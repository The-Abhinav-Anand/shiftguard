"""Integration tests for Gate 4 PostgreSQL 16 backend contracts (I02, I04, I07).

Executes against the live PostgreSQL 16 test service with isolated, disposable schemas
and real concurrency barriers (no mocks).
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import threading
import time
from uuid import uuid4

from alembic import command
import pytest
from sqlalchemy import create_engine, text
from starlette.testclient import TestClient

from shiftguard.api.main import create_app
from shiftguard.jobs.models import JobStatus, utc_now_str
from shiftguard.jobs.queue import IdempotencyConflictError, JobQueue, QuotaExceededError
from shiftguard.jobs.recovery import recover_expired_leases
from shiftguard.jobs.worker import ExperimentWorker
from shiftguard.migrations import get_alembic_config, upgrade_database
from shiftguard.settings import Settings
from shiftguard.storage.db import create_engine_for_settings
from shiftguard.storage.repositories import ExperimentRepository


@pytest.fixture
def pg_schema(tmp_path):
    """Provide an isolated, disposable schema in the live PostgreSQL 16 test database."""
    url = os.environ.get("SHIFTGUARD_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("BLOCKED: isolated PostgreSQL 16 test URL is missing")

    admin = create_engine(url)
    with admin.begin() as conn:
        version = conn.execute(text("SHOW server_version_num")).scalar_one()
        assert version.startswith("16"), f"Expected PostgreSQL 16, got {version}"
        schema = "sg_bcontracts_" + uuid4().hex[:16]
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    admin.dispose()

    schema_url = f"{url}?options=-csearch_path%3D{schema}"
    settings = Settings(
        SHIFTGUARD_DB_URL=schema_url,
        SHIFTGUARD_ENVIRONMENT="hosted",
        SHIFTGUARD_ARTIFACT_ROOT=str(tmp_path / "artifacts"),
        SHIFTGUARD_EMBEDDED_WORKER=False,
    )
    upgrade_database(settings)
    engine = create_engine_for_settings(settings)
    try:
        yield settings, schema_url, engine, schema
    finally:
        engine.dispose()
        admin = create_engine(url)
        with admin.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


# ===========================================================================
# I02: Admission Quota, Idempotency Replay, Isolation, and Config Persistence
# ===========================================================================

def test_i02_postgres_concurrent_admission_quota_strictly_two(pg_schema):
    """I02: Concurrent submitters cannot admit more than two active jobs for one session on PostgreSQL 16."""
    settings, schema_url, engine, schema = pg_schema

    # Create session
    app = create_app(settings)
    with TestClient(app) as client:
        s_res = client.post("/api/v1/agent/sessions", json={})
        assert s_res.status_code == 201
        sid = s_res.json()["session_id"]

    def _enqueue_unique(idx: int):
        eng = create_engine(schema_url)
        queue = JobQueue(eng)
        try:
            job = queue.enqueue(
                payload_hash=f"hash-pg-unique-{idx}",
                request_params={"preset_name": f"preset-{idx}"},
                session_id=sid,
                idempotency_key=f"idem-pg-unique-{idx}",
            )
            return ("SUCCESS", job.id)
        except QuotaExceededError as e:
            return ("QUOTA_EXCEEDED", str(e))
        finally:
            eng.dispose()

    # Launch 6 concurrent submission attempts
    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = [executor.submit(_enqueue_unique, i) for i in range(6)]
        results = [f.result() for f in futures]

    successes = [r for r in results if r[0] == "SUCCESS"]
    quota_exceeded = [r for r in results if r[0] == "QUOTA_EXCEEDED"]

    # Exactly 2 succeed, exactly 4 are rejected by PostgreSQL FOR UPDATE row lock
    assert len(successes) == 2, f"Expected 2 successes, got {len(successes)}"
    assert len(quota_exceeded) == 4, f"Expected 4 quota exceeded, got {len(quota_exceeded)}"

    with engine.connect() as conn:
        active_count = conn.execute(
            text("SELECT count(*) FROM jobs WHERE session_id = :sid AND status IN ('queued', 'running')"),
            {"sid": sid},
        ).scalar()
        assert active_count == 2


def test_i02_postgres_same_key_retries_replay_one_job(pg_schema):
    """I02: Same-key retries replay one job concurrently on PostgreSQL 16."""
    settings, schema_url, engine, schema = pg_schema

    app = create_app(settings)
    with TestClient(app) as client:
        s_res = client.post("/api/v1/agent/sessions", json={})
        sid = s_res.json()["session_id"]

    idem_key = "idem-pg-replay-key"
    payload_hash = "payload-hash-pg-same"

    def _enqueue_same(idx: int):
        eng = create_engine(schema_url)
        queue = JobQueue(eng)
        try:
            job = queue.enqueue(
                payload_hash=payload_hash,
                request_params={"preset_name": "bank-outage-50"},
                session_id=sid,
                idempotency_key=idem_key,
            )
            return job.id
        finally:
            eng.dispose()

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(_enqueue_same, i) for i in range(8)]
        results = [f.result() for f in futures]

    # All 8 concurrent callers receive the same winning job ID
    assert len(set(results)) == 1
    winning_job_id = results[0]

    with engine.connect() as conn:
        count = conn.execute(text("SELECT count(*) FROM jobs WHERE session_id = :sid"), {"sid": sid}).scalar()
        assert count == 1
        j_id = conn.execute(text("SELECT id FROM jobs WHERE session_id = :sid"), {"sid": sid}).scalar()
        assert j_id == winning_job_id


def test_i02_postgres_cross_session_cannot_inspect_or_cancel(pg_schema):
    """I02: Another session cannot inspect or cancel a job on PostgreSQL 16."""
    settings, _, _, _ = pg_schema

    app = create_app(settings)
    with TestClient(app) as client:
        # Create session 1
        s1 = client.post("/api/v1/agent/sessions", json={}).json()
        s1_headers = {"X-Session-ID": s1["session_id"], "X-Session-Token": s1["capability_token"]}

        # Create session 2
        s2 = client.post("/api/v1/agent/sessions", json={}).json()
        s2_headers = {"X-Session-ID": s2["session_id"], "X-Session-Token": s2["capability_token"]}

        # Session 1 submits job
        sub = client.post("/api/v1/experiments", json={"preset_name": "bank-outage-50"}, headers=s1_headers)
        assert sub.status_code == 202
        job_id = sub.json()["job_id"]

        # Session 2 attempts read -> 403 Forbidden
        read_s2 = client.get(f"/api/v1/jobs/{job_id}", headers=s2_headers)
        assert read_s2.status_code == 403
        assert read_s2.json()["error"]["code"] == "CROSS_SESSION_ACCESS_DENIED"

        # Session 2 attempts cancel -> 403 Forbidden
        cancel_s2 = client.post(f"/api/v1/jobs/{job_id}/cancel", headers=s2_headers)
        assert cancel_s2.status_code == 403
        assert cancel_s2.json()["error"]["code"] == "CROSS_SESSION_ACCESS_DENIED"

        # Session 1 reads own job -> 200 OK
        read_s1 = client.get(f"/api/v1/jobs/{job_id}", headers=s1_headers)
        assert read_s1.status_code == 200
        assert read_s1.json()["job_id"] == job_id

        # Session 1 cancels own job -> 202 Accepted
        cancel_s1 = client.post(f"/api/v1/jobs/{job_id}/cancel", headers=s1_headers)
        assert cancel_s1.status_code == 202


def test_i02_postgres_submitted_configuration_reaches_persisted_result(pg_schema):
    """I02: Submitted configuration reaches the persisted experiment result on PostgreSQL 16."""
    settings, schema_url, engine, _ = pg_schema
    queue = JobQueue(engine)
    app = create_app(settings)
    submitted_params = {"preset_name": "bank-outage-50", "overrides": {"seed": 31002}}
    with TestClient(app) as client:
        session = client.post("/api/v1/agent/sessions", json={}).json()
        headers = {
            "X-Session-ID": session["session_id"],
            "X-Session-Token": session["capability_token"],
        }
        response = client.post("/api/v1/experiments", json=submitted_params, headers=headers)
        assert response.status_code == 202, response.text
        job_id = response.json()["job_id"]

    # Worker processes the job
    worker = ExperimentWorker(settings=settings)
    executed = worker.run_once(queue)
    assert executed is not None

    updated_job = queue.get_job(job_id)
    assert updated_job.status == JobStatus.COMPLETED
    assert updated_job.experiment_id is not None
    assert updated_job.result is not None
    with engine.connect() as conn:
        persisted_request = conn.execute(
            text("SELECT request_params_json FROM jobs WHERE id = :job_id"),
            {"job_id": job_id},
        ).scalar_one()
    persisted_params = json.loads(persisted_request)
    assert persisted_params["preset_name"] == submitted_params["preset_name"]
    assert persisted_params["overrides"] == submitted_params["overrides"]

    # Verify persisted in experiments table
    repo = ExperimentRepository(engine)
    published = repo.get_published(updated_job.experiment_id)
    assert published is not None
    stored_exp, pub_rec = published
    assert stored_exp.experiment_id == updated_job.experiment_id
    assert pub_rec.status == "PUBLISHED"
    assert "config" in stored_exp.deterministic_payload
    assert stored_exp.deterministic_payload["config"]["master_seed"] == 31002
    with engine.connect() as conn:
        publication_job_id = conn.execute(
            text("SELECT job_id FROM experiment_publications WHERE experiment_id = :experiment_id"),
            {"experiment_id": updated_job.experiment_id},
        ).scalar_one()
        execution = conn.execute(
            text("SELECT execution_id, experiment_id FROM experiment_executions WHERE execution_id = :execution_id"),
            {"execution_id": pub_rec.execution_id},
        ).mappings().one()
    assert publication_job_id == job_id
    assert dict(execution) == {
        "execution_id": pub_rec.execution_id,
        "experiment_id": updated_job.experiment_id,
    }
    assert "acquisition" in stored_exp.deterministic_payload


# ===========================================================================
# I04: Single Owner Claims, Expired Fencing, Cancellation Races, & Lifespan Worker
# ===========================================================================

def test_i04_postgres_concurrent_claims_have_single_owner(pg_schema):
    """I04: Concurrent claims on PostgreSQL 16 have exactly one winner via FOR UPDATE SKIP LOCKED."""
    settings, schema_url, engine, _ = pg_schema

    queue = JobQueue(engine)
    job = queue.enqueue({"preset_name": "bank-outage-50"})

    barrier = threading.Barrier(5)
    claimed_results = []
    lock = threading.Lock()

    def _attempt_claim(worker_idx: int):
        eng = create_engine(schema_url)
        q = JobQueue(eng)
        try:
            barrier.wait()
            claimed = q.claim_next_job(f"worker-{worker_idx}", lease_seconds=60)
            with lock:
                claimed_results.append((worker_idx, claimed))
        finally:
            eng.dispose()

    threads = [threading.Thread(target=_attempt_claim, args=(i,)) for i in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    winners = [c for c in claimed_results if c[1] is not None]
    losers = [c for c in claimed_results if c[1] is None]

    assert len(winners) == 1, f"Expected exactly 1 claim winner, got {len(winners)}"
    assert len(losers) == 4, f"Expected 4 claim losers, got {len(losers)}"

    winner_worker, claimed_job = winners[0]
    assert claimed_job.id == job.id
    assert claimed_job.worker_id == f"worker-{winner_worker}"
    assert claimed_job.fencing_token is not None


def test_i04_postgres_expired_or_replaced_owners_cannot_heartbeat_or_finish(pg_schema):
    """I04: Expired or replaced owners cannot heartbeat or finish on PostgreSQL 16."""
    settings, schema_url, engine, _ = pg_schema

    queue = JobQueue(engine)
    job = queue.enqueue({"preset_name": "bank-outage-50"})
    claimed = queue.claim_next_job("worker-1", lease_seconds=1)
    assert claimed is not None
    token = claimed.fencing_token

    # Manually expire lease in PostgreSQL
    past_time = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE jobs SET lease_expires_at = :past WHERE id = :id"),
            {"past": past_time, "id": job.id},
        )

    # Recover expired lease (requeues job)
    recovered = recover_expired_leases(queue)
    assert recovered == 1

    # Stale worker attempts heartbeat -> rejected
    hb_success = queue.heartbeat(job.id, fencing_token=token, lease_seconds=60)
    assert hb_success is False

    # Stale worker attempts mark_completed -> rejected
    comp_success = queue.mark_completed(
        job_id=job.id,
        fencing_token=token,
        experiment_id="exp-stale",
        result_data={"status": "ok"},
    )
    assert comp_success is False

    # Job is queued (not completed by stale worker)
    fresh = queue.get_job(job.id)
    assert fresh.status == JobStatus.QUEUED
    assert fresh.completed_at is None


def test_i04_postgres_cancellation_survives_completion_race(pg_schema):
    """I04: Cancellation and completion serialize safely on PostgreSQL 16."""
    settings, schema_url, engine, _ = pg_schema

    queue = JobQueue(engine)
    job = queue.enqueue({"preset_name": "bank-outage-50"})
    claimed = queue.claim_next_job("worker-1", lease_seconds=60)
    token = claimed.fencing_token

    barrier = threading.Barrier(2)
    results = {}

    def _cancel():
        eng = create_engine(schema_url)
        q = JobQueue(eng)
        try:
            barrier.wait()
            results["cancel"] = q.request_cancellation(job.id)[0]
        finally:
            eng.dispose()

    def _complete():
        eng = create_engine(schema_url)
        q = JobQueue(eng)
        try:
            barrier.wait()
            results["complete"] = q.mark_completed(
                job_id=job.id,
                fencing_token=token,
                experiment_id="exp-race-pg",
                result_data={"status": "ok"},
            )
        finally:
            eng.dispose()

    t1 = threading.Thread(target=_cancel)
    t2 = threading.Thread(target=_complete)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    fresh = queue.get_job(job.id)
    # Either completion won before cancellation, OR cancellation prevented completion
    if results["complete"] is True:
        assert fresh.status == JobStatus.COMPLETED
    else:
        assert fresh.cancel_requested is True


@pytest.mark.parametrize("exhausted", [False, True], ids=["retry-available", "attempts-exhausted"])
def test_i04_postgres_recovery_observes_cancellation_after_expired_selection(pg_schema, exhausted):
    """A cancellation committed after lease selection wins both recovery transitions."""
    from sqlalchemy import event

    _, schema_url, engine, _ = pg_schema
    queue = JobQueue(engine)
    job = queue.enqueue({"preset_name": "bank-outage-50"})
    claimed = queue.claim_next_job("worker-race", lease_seconds=60)
    assert claimed is not None

    past_time = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE jobs SET lease_expires_at = :past WHERE id = :job_id"),
            {"past": past_time, "job_id": job.id},
        )
        if exhausted:
            conn.execute(
                text("UPDATE jobs SET max_attempts = attempt WHERE id = :job_id"),
                {"job_id": job.id},
            )

    cancellation = {}
    fired = False

    def cancel_after_selection(conn, cursor, statement, parameters, context, executemany):
        nonlocal fired
        normalized = " ".join(statement.lower().split())
        if not fired and normalized.startswith("select id, attempt, max_attempts, cancel_requested, fencing_token from jobs"):
            fired = True
            cancel_engine = create_engine(schema_url)
            try:
                cancellation["result"] = JobQueue(cancel_engine).request_cancellation(job.id)
            finally:
                cancel_engine.dispose()

    event.listen(engine, "after_cursor_execute", cancel_after_selection)
    try:
        assert recover_expired_leases(queue) == 1
    finally:
        event.remove(engine, "after_cursor_execute", cancel_after_selection)

    assert fired is True
    assert cancellation["result"] == (True, "cancel_requested")
    fresh = queue.get_job(job.id)
    assert fresh.status == JobStatus.CANCELLED
    assert fresh.cancel_requested is True
    assert fresh.completed_at is not None
    assert not (fresh.status == JobStatus.QUEUED and fresh.cancel_requested)

    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT event_type, fencing_token FROM job_events WHERE job_id = :job_id ORDER BY created_at, id"),
            {"job_id": job.id},
        ).mappings().all()
    event_types = [row["event_type"] for row in rows]
    assert event_types.count("CANCEL_REQUESTED") == 1
    assert event_types.count("CANCELLED") == 1
    assert "REQUEUED" not in event_types
    assert "FAILED" not in event_types
    cancelled_event = next(row for row in rows if row["event_type"] == "CANCELLED")
    assert cancelled_event["fencing_token"] == claimed.fencing_token


def test_i04_postgres_http_submission_completes_through_managed_worker(pg_schema):
    """I04: HTTP submission completes through the managed worker lifespan on PostgreSQL 16."""
    _, schema_url, _, _ = pg_schema

    tmp_artifacts = Path(os.environ.get("TEMP", "/tmp")) / f"sg_art_{uuid4().hex[:8]}"
    tmp_artifacts.mkdir(parents=True, exist_ok=True)

    settings = Settings(
        SHIFTGUARD_DB_URL=schema_url,
        SHIFTGUARD_ENVIRONMENT="hosted",
        SHIFTGUARD_ARTIFACT_ROOT=str(tmp_artifacts),
        SHIFTGUARD_EMBEDDED_WORKER=True,
        SHIFTGUARD_WORKER_POLL_INTERVAL=0.1,
        SHIFTGUARD_RECOVERY_INTERVAL=1.0,
    )
    app = create_app(settings)

    with TestClient(app) as client:
        # Create session
        s_res = client.post("/api/v1/agent/sessions", json={})
        assert s_res.status_code == 201
        sid = s_res.json()["session_id"]
        stoken = s_res.json()["capability_token"]
        headers = {"X-Session-ID": sid, "X-Session-Token": stoken}

        # Submit experiment
        sub_res = client.post("/api/v1/experiments", json={"preset_name": "bank-outage-50"}, headers=headers)
        assert sub_res.status_code == 202
        job_id = sub_res.json()["job_id"]
        status_url = sub_res.json()["status_url"]

        # Autonomous completion via lifespan background worker
        max_wait = 30.0
        start = time.time()
        final_data = None
        while time.time() - start < max_wait:
            res = client.get(status_url, headers=headers)
            assert res.status_code == 200
            data = res.json()
            if data["status"] in ("completed", "failed"):
                final_data = data
                break
            time.sleep(0.2)

        assert final_data is not None, f"Job {job_id} did not complete within {max_wait}s"
        assert final_data["status"] == "completed", f"Job failed: {final_data.get('error')}"
        assert final_data["experiment_id"] is not None

        # Verify retrievable via public API
        exp_id = final_data["experiment_id"]
        exp_res = client.get(f"/api/v1/experiments/{exp_id}")
        assert exp_res.status_code == 200
        assert exp_res.json()["experiment_id"] == exp_id


# ===========================================================================
# I07: Migration Upgrade Path 0005 to 0008 on PostgreSQL 16
# ===========================================================================

def test_i07_postgres_migration_upgrade_0005_to_0008_preserves_rows(pg_schema):
    """I07: Existing 0005 database with sessions/jobs/idempotency upgrades to 0008 on PostgreSQL 16."""
    _, schema_url, _, schema = pg_schema
    url = os.environ["SHIFTGUARD_TEST_POSTGRES_URL"]

    # Create a fresh isolated schema specifically for migration upgrade
    upgrade_schema = f"sg_mig_{uuid4().hex[:12]}"
    admin = create_engine(url)
    with admin.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{upgrade_schema}"'))
    admin.dispose()

    mig_url = f"{url}?options=-csearch_path%3D{upgrade_schema}"
    settings = Settings(SHIFTGUARD_DB_URL=mig_url, SHIFTGUARD_ENVIRONMENT="hosted")
    config = get_alembic_config(settings)

    try:
        # 1. Upgrade only to 0005
        engine = create_engine_for_settings(settings)
        with engine.connect() as conn:
            config.attributes["connection"] = conn
            command.upgrade(config, "0005_gate4_jobs_and_continuation")

        # 2. Insert representative rows in 0005 schema format
        with engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO agent_sessions (
                        id, status, active_nonce, required_job_ids_json, state_json, created_at, updated_at
                    ) VALUES (
                        'sess-pg-001', 'active', 'nonce-pg-001', '[]', '{}', '2026-09-18T12:00:00Z', '2026-09-18T12:00:00Z'
                    )
                """)
            )
            conn.execute(
                text("""
                    INSERT INTO jobs (
                        id, session_id, payload_hash, status, request_params_json, attempt, max_attempts, cancel_requested, created_at
                    ) VALUES (
                        'job-pg-001', 'sess-pg-001', 'hash-pg-001', 'queued', '{}', 0, 3, false, '2026-09-18T12:00:00Z'
                    )
                """)
            )
            # Legacy 0005 idempotency_records (no scope column, single PK on key)
            conn.execute(
                text("""
                    INSERT INTO idempotency_records (
                        key, payload_hash, job_id, response_code, response_json, created_at
                    ) VALUES (
                        'idem-key-pg-1', 'hash-pg-001', 'job-pg-001', 202, '{"job_id": "job-pg-001"}', '2026-09-18T12:00:00Z'
                    )
                """)
            )
            # Standalone job without session
            conn.execute(
                text("""
                    INSERT INTO jobs (
                        id, session_id, payload_hash, status, request_params_json, attempt, max_attempts, cancel_requested, created_at
                    ) VALUES (
                        'job-pg-global', NULL, 'hash-pg-global', 'queued', '{}', 0, 3, false, '2026-09-18T12:00:00Z'
                    )
                """)
            )
            conn.execute(
                text("""
                    INSERT INTO idempotency_records (
                        key, payload_hash, job_id, response_code, response_json, created_at
                    ) VALUES (
                        'idem-key-pg-global', 'hash-pg-global', 'job-pg-global', 202, '{"job_id": "job-pg-global"}', '2026-09-18T12:00:00Z'
                    )
                """)
            )

        # 3. Upgrade to head (0008)
        with engine.connect() as conn:
            config.attributes["connection"] = conn
            command.upgrade(config, "head")

        # 4. Verify preserved rows and backfilled columns on PostgreSQL 16
        with engine.connect() as conn:
            # Check idempotency record for job with session has scope = 'sess-pg-001'
            idem_row = conn.execute(
                text("SELECT scope, key, payload_hash, job_id FROM idempotency_records WHERE key = 'idem-key-pg-1'")
            ).mappings().fetchone()
            assert idem_row is not None
            assert idem_row["scope"] == "sess-pg-001"
            assert idem_row["job_id"] == "job-pg-001"

            preserved_jobs = conn.execute(text("SELECT * FROM jobs ORDER BY id")).mappings().all()
            expected_job_fields = {
                "experiment_id": None,
                "idempotency_key": None,
                "status": "queued",
                "request_params_json": "{}",
                "worker_id": None,
                "fencing_token": None,
                "attempt": 0,
                "max_attempts": 3,
                "lease_expires_at": None,
                "heartbeat_at": None,
                "cancel_requested": False,
                "error_json": None,
                "result_json": None,
                "created_at": "2026-09-18T12:00:00Z",
                "started_at": None,
                "completed_at": None,
            }
            assert [dict(job) for job in preserved_jobs] == [
                {**expected_job_fields, "id": "job-pg-001", "session_id": "sess-pg-001", "payload_hash": "hash-pg-001"},
                {**expected_job_fields, "id": "job-pg-global", "session_id": None, "payload_hash": "hash-pg-global"},
            ]

            # Check idempotency record for job without session has scope = 'global'
            idem_global = conn.execute(
                text("SELECT scope, key, payload_hash, job_id FROM idempotency_records WHERE key = 'idem-key-pg-global'")
            ).mappings().fetchone()
            assert idem_global is not None
            assert idem_global["scope"] == "global"
            assert idem_global["job_id"] == "job-pg-global"

            # Check capability_token column exists in agent_sessions and legacy session is marked expired
            session_row = conn.execute(
                text("SELECT id, status, capability_token FROM agent_sessions WHERE id = 'sess-pg-001'")
            ).mappings().fetchone()
            assert session_row is not None
            assert "capability_token" in session_row
            assert session_row["status"] == "expired"

            # Check continuation_receipts table exists
            receipts_count = conn.execute(text("SELECT COUNT(*) FROM continuation_receipts")).scalar()
            assert receipts_count == 0

            # Check publication table has attempt and fencing_token columns
            pub_cols = [c[0] for c in conn.execute(text(
                "SELECT column_name FROM information_schema.columns WHERE table_schema = :s AND table_name = 'experiment_publications'"
            ), {"s": upgrade_schema}).fetchall()]
            assert "job_id" in pub_cols
            assert "lease_expires_at" in pub_cols
            assert "attempt" in pub_cols
            assert "fencing_token" in pub_cols

            # Check inserting a scoped idempotency record with same key but different scope succeeds
            with engine.begin() as write_conn:
                write_conn.execute(
                    text("""
                        INSERT INTO idempotency_records (
                            scope, key, payload_hash, job_id, response_code, response_json, created_at
                        ) VALUES (
                            'sess-pg-002', 'idem-key-pg-1', 'hash-pg-002', 'job-pg-002', 202, '{"job_id": "job-pg-002"}', '2026-09-18T12:05:00Z'
                        )
                    """)
                )

            scoped_row = conn.execute(
                text("SELECT scope, key, job_id FROM idempotency_records WHERE scope = 'sess-pg-002' AND key = 'idem-key-pg-1'")
            ).mappings().fetchone()
            assert scoped_row is not None
            assert scoped_row["job_id"] == "job-pg-002"

        engine.dispose()
    finally:
        admin = create_engine(url)
        with admin.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{upgrade_schema}" CASCADE'))
        admin.dispose()
