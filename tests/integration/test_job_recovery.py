"""Integration tests for worker claim concurrency, fencing tokens, lease recovery, and staging cleanup."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import time
import pytest
from sqlalchemy import create_engine, text

from shiftguard.jobs.models import JobStatus, utc_now_str
from shiftguard.jobs.queue import JobQueue
from shiftguard.jobs.recovery import cleanup_abandoned_staging, recover_expired_leases
from shiftguard.migrations import upgrade_database
from shiftguard.settings import Settings


@pytest.fixture
def queue_and_engine(tmp_path):
    db_file = tmp_path / "recovery_test.db"
    settings = Settings(SHIFTGUARD_DB_URL=f"sqlite:///{db_file}")
    upgrade_database(settings)
    engine = create_engine(f"sqlite:///{db_file}")
    try:
        yield JobQueue(engine), engine
    finally:
        engine.dispose()


def test_atomic_claim_and_fencing_token(queue_and_engine):
    queue, engine = queue_and_engine
    job = queue.enqueue({"preset_name": "bank-outage-50"})

    # Worker 1 claims
    claimed = queue.claim_next_job(worker_id="worker-alpha", lease_seconds=60)
    assert claimed is not None
    assert claimed.id == job.id
    assert claimed.status == JobStatus.RUNNING
    assert claimed.worker_id == "worker-alpha"
    assert claimed.attempt == 1
    assert claimed.fencing_token is not None
    token1 = claimed.fencing_token

    # Worker 2 attempts claim; queue is empty
    claimed2 = queue.claim_next_job(worker_id="worker-beta", lease_seconds=60)
    assert claimed2 is None

    # Heartbeat with valid token succeeds
    assert queue.heartbeat(job.id, token1, lease_seconds=60) is True

    # Heartbeat with stale/wrong token is rejected
    assert queue.heartbeat(job.id, "stale-fake-token", lease_seconds=60) is False


def test_recover_expired_leases_requeues_below_max_attempts(queue_and_engine):
    queue, engine = queue_and_engine
    job = queue.enqueue({"preset_name": "bank-outage-50"}, max_attempts=3)

    # Claim job
    claimed = queue.claim_next_job(worker_id="worker-crashed", lease_seconds=60)
    assert claimed.attempt == 1

    # Artificially expire lease in database
    past_str = (datetime.now(timezone.utc) - timedelta(seconds=120)).isoformat()
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE jobs SET lease_expires_at = :past WHERE id = :id"),
            {"past": past_str, "id": job.id},
        )

    # Recover expired leases
    recovered = recover_expired_leases(queue)
    assert recovered == 1

    # Check job is requeued
    requeued_job = queue.get_job(job.id)
    assert requeued_job.status == JobStatus.QUEUED
    assert requeued_job.worker_id is None
    assert requeued_job.fencing_token is None

    # Next claim receives attempt 2
    claimed_again = queue.claim_next_job(worker_id="worker-fresh", lease_seconds=60)
    assert claimed_again.id == job.id
    assert claimed_again.attempt == 2


def test_recover_expired_leases_fails_at_max_attempts(queue_and_engine):
    queue, engine = queue_and_engine
    job = queue.enqueue({"preset_name": "bank-outage-50"}, max_attempts=1)

    claimed = queue.claim_next_job(worker_id="worker-crashed", lease_seconds=60)
    assert claimed.attempt == 1

    # Artificially expire lease
    past_str = (datetime.now(timezone.utc) - timedelta(seconds=120)).isoformat()
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE jobs SET lease_expires_at = :past WHERE id = :id"),
            {"past": past_str, "id": job.id},
        )

    recovered = recover_expired_leases(queue)
    assert recovered == 1

    failed_job = queue.get_job(job.id)
    assert failed_job.status == JobStatus.FAILED
    assert failed_job.error["code"] == "LEASE_EXPIRED_MAX_ATTEMPTS"


def test_cleanup_abandoned_staging(tmp_path):
    artifact_root = tmp_path / "artifacts"
    staging_dir = artifact_root / ".staging"
    staging_dir.mkdir(parents=True, exist_ok=True)

    abandoned = staging_dir / "abandoned_execution_uuid"
    abandoned.mkdir(parents=True, exist_ok=True)
    (abandoned / "partial.json").write_text("{}", encoding="utf-8")

    # If max_age is large, not cleaned
    assert cleanup_abandoned_staging(artifact_root, max_age_seconds=1000) == 0
    assert abandoned.is_dir()

    # If max_age is 0, cleaned
    time.sleep(0.05)
    assert cleanup_abandoned_staging(artifact_root, max_age_seconds=0) == 1
    assert not abandoned.exists()
