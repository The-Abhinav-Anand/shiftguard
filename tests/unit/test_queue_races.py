"""Unit tests for Gate 4 queue transition race safety and barrier probes."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
import threading
import time
import pytest
from sqlalchemy import create_engine, text

from shiftguard.jobs.models import JobStatus, utc_now_str
from shiftguard.jobs.queue import JobQueue
from shiftguard.jobs.recovery import recover_expired_leases
from shiftguard.migrations import upgrade_database
from shiftguard.settings import Settings


@pytest.fixture
def queue_fixture(tmp_path):
    db_file = tmp_path / "races.db"
    settings = Settings(SHIFTGUARD_DB_URL=f"sqlite:///{db_file}")
    upgrade_database(settings)
    engine = create_engine(f"sqlite:///{db_file}")
    try:
        yield JobQueue(engine), engine
    finally:
        engine.dispose()


def test_expired_lease_completion_is_rejected(queue_fixture):
    """G4-02: A worker with an expired lease cannot mark the job completed."""
    queue, engine = queue_fixture
    job = queue.enqueue({"preset_name": "bank-outage-50"})
    
    # Claim job with 1-second lease
    claimed = queue.claim_next_job("worker-1", lease_seconds=1)
    assert claimed is not None
    assert claimed.id == job.id
    token = claimed.fencing_token

    # Manually expire the lease in the DB
    past_time = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE jobs SET lease_expires_at = :past WHERE id = :id"),
            {"past": past_time, "id": job.id},
        )

    # Attempt completion with expired lease -> must return False / be rejected
    success = queue.mark_completed(
        job_id=job.id,
        fencing_token=token,
        experiment_id="exp-123",
        result_data={"result": "ok"},
    )
    assert success is False

    # Status must still be running (not completed)
    fresh = queue.get_job(job.id)
    assert fresh.status == JobStatus.RUNNING
    assert fresh.completed_at is None


def test_cancelled_job_completion_is_rejected(queue_fixture):
    """G4-02: Completion of a job after cancellation request must be rejected."""
    queue, engine = queue_fixture
    job = queue.enqueue({"preset_name": "bank-outage-50"})
    
    claimed = queue.claim_next_job("worker-1", lease_seconds=60)
    assert claimed is not None
    token = claimed.fencing_token

    # User requests cancellation
    success, res = queue.request_cancellation(job.id)
    assert success is True
    assert res == "cancel_requested"

    # Worker attempts completion -> must return False because cancel_requested is True
    complete_success = queue.mark_completed(
        job_id=job.id,
        fencing_token=token,
        experiment_id="exp-123",
        result_data={"result": "ok"},
    )
    assert complete_success is False

    fresh = queue.get_job(job.id)
    assert fresh.status == JobStatus.RUNNING
    assert fresh.cancel_requested is True
    assert fresh.completed_at is None


def test_heartbeat_after_recovery_is_fenced_out(queue_fixture):
    """G4-02: Worker heartbeat fails after recovery has requeued or failed the expired job."""
    queue, engine = queue_fixture
    job = queue.enqueue({"preset_name": "bank-outage-50"})
    
    claimed = queue.claim_next_job("worker-1", lease_seconds=1)
    token = claimed.fencing_token

    # Expire lease
    past_time = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE jobs SET lease_expires_at = :past WHERE id = :id"),
            {"past": past_time, "id": job.id},
        )

    # Recovery runs and requeues job
    recovered = recover_expired_leases(queue)
    assert recovered == 1

    # Stale worker tries to heartbeat -> must return False (fenced out)
    hb_success = queue.heartbeat(job.id, fencing_token=token, lease_seconds=60)
    assert hb_success is False

    # Job is now queued, not running under worker-1
    fresh = queue.get_job(job.id)
    assert fresh.status == JobStatus.QUEUED
    assert fresh.worker_id is None


def test_threaded_barrier_race_heartbeat_vs_recovery(queue_fixture):
    """G4-02: Simultaneous heartbeat and recovery synchronization via barrier."""
    queue, engine = queue_fixture
    job = queue.enqueue({"preset_name": "bank-outage-50"})
    
    claimed = queue.claim_next_job("worker-1", lease_seconds=1)
    token = claimed.fencing_token

    # Set lease to expire exactly now
    past_time = (datetime.now(timezone.utc) - timedelta(milliseconds=100)).isoformat()
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE jobs SET lease_expires_at = :past WHERE id = :id"),
            {"past": past_time, "id": job.id},
        )

    barrier = threading.Barrier(2)
    results = {}

    def _worker_hb():
        barrier.wait()
        results["hb"] = queue.heartbeat(job.id, fencing_token=token, lease_seconds=60)

    def _recovery_run():
        barrier.wait()
        results["rec"] = recover_expired_leases(queue)

    t1 = threading.Thread(target=_worker_hb)
    t2 = threading.Thread(target=_recovery_run)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    # Either heartbeat won before recovery, or recovery won before heartbeat.
    # In neither case can both succeed with conflicting states:
    fresh = queue.get_job(job.id)
    if results["rec"] == 1:
        # Recovery won: job was requeued
        assert fresh.status in (JobStatus.QUEUED, JobStatus.FAILED)
    else:
        # Heartbeat won: lease was renewed before recovery checked
        assert results["hb"] is True
        assert fresh.status == JobStatus.RUNNING


def test_threaded_barrier_race_cancel_vs_complete(queue_fixture):
    """G4-02: Simultaneous cancellation request and completion attempt."""
    queue, engine = queue_fixture
    job = queue.enqueue({"preset_name": "bank-outage-50"})
    claimed = queue.claim_next_job("worker-1", lease_seconds=60)
    token = claimed.fencing_token

    barrier = threading.Barrier(2)
    results = {}

    def _cancel():
        barrier.wait()
        results["cancel"] = queue.request_cancellation(job.id)[0]

    def _complete():
        barrier.wait()
        results["complete"] = queue.mark_completed(
            job_id=job.id,
            fencing_token=token,
            experiment_id="exp-race",
            result_data={"status": "ok"},
        )

    t1 = threading.Thread(target=_cancel)
    t2 = threading.Thread(target=_complete)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    fresh = queue.get_job(job.id)
    # If complete succeeded, status must be COMPLETED
    # If cancel was committed before complete, complete MUST return False
    if results["complete"] is True:
        assert fresh.status == JobStatus.COMPLETED
    else:
        assert fresh.cancel_requested is True
