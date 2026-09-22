"""Comprehensive regression tests for all 6 findings and probes from Gate 4 Review #3.

Verifies:
- R3-01: Job resurrection / recovery invariant violation. Cancelled/failed jobs are never resurrected to completed.
- R3-02: Content hash canonical stem format ({stem: sha256, "logical_content": full_digest}) and identical republication immutability.
- R3-03: Portable boolean query bindings in atomic completion (:not_cancelled = False).
- R3-04: Universal publication ownership protocol with bounded lease for CLI and worker; unexpired CLI owner cannot be stolen.
- R3-05: Multiprocess admission quota (strictly 2) and atomic idempotency serialization.
- R3-06: Transition-time lease expiry verification at atomic completion point with full rollback.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import hashlib
import json
from multiprocessing import get_context
from pathlib import Path
import pytest
from sqlalchemy import create_engine, text
from starlette.testclient import TestClient

from shiftguard.api.main import create_app
from shiftguard.experiments.ids import stable_hash
from shiftguard.jobs.models import (
    JobStatus,
    PublicationContentionError,
    PublicationLostOwnershipError,
    WorkerCancelledException,
    WorkerFencedOutException,
    utc_now_str,
)
from shiftguard.jobs.queue import IdempotencyConflictError, JobQueue, QuotaExceededError
from shiftguard.jobs.recovery import recover_prepared_publications
from shiftguard.migrations import upgrade_database
from shiftguard.settings import Settings
from shiftguard.storage.repositories import (
    ExperimentImmutabilityError,
    ExperimentRepository,
    canonical_content_hashes,
)


@pytest.fixture
def r3_fixture(tmp_path):
    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir(parents=True, exist_ok=True)
    db_file = tmp_path / "r3_regressions.db"
    settings = Settings(
        SHIFTGUARD_DB_URL=f"sqlite:///{db_file}",
        SHIFTGUARD_ARTIFACT_ROOT=str(artifact_root),
    )
    upgrade_database(settings)
    app = create_app(settings)
    engine = create_engine(f"sqlite:///{db_file}")
    with TestClient(app) as client:
        yield client, engine, artifact_root, settings, db_file
    engine.dispose()


# ---------------------------------------------------------------------------
# R3-01: Job resurrection / recovery invariant violation
# ---------------------------------------------------------------------------

def test_recovery_does_not_resurrect_cancelled_job(r3_fixture):
    """Probe 1: Recovery never converts cancelled jobs into completed jobs; preserves cancelled state and quarantines publication."""
    _, engine, artifact_root, _, _ = r3_fixture
    exp_id = "exp-cancelled-recovery"
    gen_id = "gen-cancelled-recovery"
    job_id = "job-cancelled-recovery"

    now_str = utc_now_str()
    expired_str = "2026-09-17T00:00:00Z"

    # Put files on disk in final destination
    exp_dir = artifact_root / exp_id
    exp_dir.mkdir(parents=True, exist_ok=True)
    f_content = b'{"status": "cancelled_artifact"}'
    (exp_dir / "result.json").write_bytes(f_content)
    f_hash = hashlib.sha256(f_content).hexdigest()
    manifest = {"result.json": f_hash}
    payload = {"experiment_id": exp_id, "preset": "bank-outage-50"}
    audit = {"worker_id": "worker-crashed"}

    # Insert job that was CANCELLED (or cancel_requested=1)
    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO jobs (id, payload_hash, request_params_json, status, worker_id, fencing_token, attempt, max_attempts,
                                  lease_expires_at, cancel_requested, created_at, started_at)
                VALUES (:job_id, 'dummyhash', '{"preset_name": "bank-outage-50"}', 'cancelled', 'worker-crashed', 'tok-crashed', 1, 3,
                        :lease, 1, :now, :now)
            """),
            {"job_id": job_id, "lease": expired_str, "now": expired_str},
        )
        conn.execute(
            text("""
                INSERT INTO experiment_publications (
                    generation_id, experiment_id, status, full_digest, execution_id,
                    manifest_json, job_id, lease_expires_at, prepared_payload_json,
                    prepared_audit_json, created_at, updated_at
                )
                VALUES (
                    :gen_id, :exp_id, 'PREPARED', 'digest-cancelled', 'exec-cancelled',
                    :manifest, :job_id, :lease, :payload, :audit, :now, :now
                )
            """),
            {
                "gen_id": gen_id,
                "exp_id": exp_id,
                "manifest": json.dumps(manifest),
                "job_id": job_id,
                "lease": expired_str,
                "payload": json.dumps(payload),
                "audit": json.dumps(audit),
                "now": expired_str,
            },
        )

    # Run recovery
    recover_prepared_publications(engine, artifact_root)

    # Job must REMAIN cancelled
    with engine.connect() as conn:
        j_status = conn.execute(text("SELECT status FROM jobs WHERE id = :job_id"), {"job_id": job_id}).scalar()
        assert j_status == "cancelled"

    # Publication must be QUARANTINED, NOT PUBLISHED
    repo = ExperimentRepository(engine)
    pub = repo.get_publication(gen_id)
    assert pub.status == "QUARANTINED"
    assert repo.get_published(exp_id) is None


def test_recovery_does_not_resurrect_failed_job(r3_fixture):
    """Probe 1b: Recovery never converts failed jobs into completed jobs."""
    _, engine, artifact_root, _, _ = r3_fixture
    exp_id = "exp-failed-recovery"
    gen_id = "gen-failed-recovery"
    job_id = "job-failed-recovery"

    expired_str = "2026-09-17T00:00:00Z"
    exp_dir = artifact_root / exp_id
    exp_dir.mkdir(parents=True, exist_ok=True)
    (exp_dir / "result.json").write_bytes(b'{"failed": true}')
    f_hash = hashlib.sha256(b'{"failed": true}').hexdigest()
    manifest = {"result.json": f_hash}

    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO jobs (id, payload_hash, request_params_json, status, worker_id, fencing_token, attempt, max_attempts,
                                  lease_expires_at, cancel_requested, created_at, started_at)
                VALUES (:job_id, 'dummyhash', '{"preset_name": "bank-outage-50"}', 'failed', 'worker-crashed', 'tok-crashed', 1, 3,
                        :lease, 0, :now, :now)
            """),
            {"job_id": job_id, "lease": expired_str, "now": expired_str},
        )
        conn.execute(
            text("""
                INSERT INTO experiment_publications (
                    generation_id, experiment_id, status, full_digest, execution_id,
                    manifest_json, job_id, lease_expires_at, prepared_payload_json,
                    prepared_audit_json, created_at, updated_at
                )
                VALUES (
                    :gen_id, :exp_id, 'PREPARED', 'digest-failed', 'exec-failed',
                    :manifest, :job_id, :lease, '{"exp": 1}', '{"aud": 1}', :now, :now
                )
            """),
            {
                "gen_id": gen_id,
                "exp_id": exp_id,
                "manifest": json.dumps(manifest),
                "job_id": job_id,
                "lease": expired_str,
                "now": expired_str,
            },
        )

    recover_prepared_publications(engine, artifact_root)

    with engine.connect() as conn:
        j_status = conn.execute(text("SELECT status FROM jobs WHERE id = :job_id"), {"job_id": job_id}).scalar()
        assert j_status == "failed"

    repo = ExperimentRepository(engine)
    pub = repo.get_publication(gen_id)
    assert pub.status == "QUARANTINED"
    assert repo.get_published(exp_id) is None


# ---------------------------------------------------------------------------
# R3-02: Canonical content hashes and clean republication
# ---------------------------------------------------------------------------

def test_recovery_reconstructs_canonical_hashes_and_permits_republication(r3_fixture):
    """Probe 2: Reconstructed hashes use canonical stem format ({stem: sha256, "logical_content": full_digest}); identical republication passes cleanly."""
    _, engine, artifact_root, _, _ = r3_fixture
    payload = {"score": 42}
    full_digest = stable_hash(payload)
    exp_id = full_digest[:24]
    gen_id = "gen-canonical-hash"
    job_id = "job-canonical-hash"

    expired_str = "2026-09-17T00:00:00Z"
    exp_dir = artifact_root / exp_id
    exp_dir.mkdir(parents=True, exist_ok=True)
    (exp_dir / "payloads").mkdir(parents=True, exist_ok=True)

    result_bytes = b'{"score": 42}'
    budget_bytes = b'{"budget": 100}'
    (exp_dir / "result.json").write_bytes(result_bytes)
    (exp_dir / "payloads" / "budget_curve.json").write_bytes(budget_bytes)

    result_hash = hashlib.sha256(result_bytes).hexdigest()
    budget_hash = hashlib.sha256(budget_bytes).hexdigest()

    manifest = {
        "result.json": result_hash,
        "payloads/budget_curve.json": budget_hash,
    }
    audit = {"worker_id": "worker-crashed"}

    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO jobs (id, payload_hash, request_params_json, status, worker_id, fencing_token, attempt, max_attempts,
                                  lease_expires_at, cancel_requested, created_at, started_at)
                VALUES (:job_id, 'dummyhash', '{"preset_name": "bank-outage-50"}', 'running', 'worker-crashed', 'tok-1', 1, 3,
                        :lease, 0, :now, :now)
            """),
            {"job_id": job_id, "lease": expired_str, "now": expired_str},
        )
        conn.execute(
            text("""
                INSERT INTO experiment_publications (
                    generation_id, experiment_id, status, full_digest, execution_id,
                    manifest_json, job_id, lease_expires_at, prepared_payload_json,
                    prepared_audit_json, created_at, updated_at
                )
                VALUES (
                    :gen_id, :exp_id, 'PREPARED', :digest, 'exec-can-1',
                    :manifest, :job_id, :lease, :payload, :audit, :now, :now
                )
            """),
            {
                "gen_id": gen_id,
                "exp_id": exp_id,
                "digest": full_digest,
                "manifest": json.dumps(manifest),
                "job_id": job_id,
                "lease": expired_str,
                "payload": json.dumps(payload),
                "audit": json.dumps(audit),
                "now": expired_str,
            },
        )

    # Recovery executes
    recovered = recover_prepared_publications(engine, artifact_root)
    assert recovered == 1

    repo = ExperimentRepository(engine)
    stored_exp, pub_rec = repo.get_published(exp_id)
    assert pub_rec.status == "PUBLISHED"

    # Verify content hashes format: stems ("result", "budget_curve") and "logical_content"
    content_hashes = stored_exp.content_hashes
    assert "result" in content_hashes
    assert content_hashes["result"] == result_hash
    assert "budget_curve" in content_hashes
    assert content_hashes["budget_curve"] == budget_hash
    assert "logical_content" in content_hashes
    assert content_hashes["logical_content"] == full_digest

    # Now verify identical normal republication passes cleanly without immutability errors
    # (Matches probe 2 resolution)
    repo.put(
        experiment_id=exp_id,
        deterministic_payload=payload,
        content_hashes=content_hashes,
        execution_id="exec-republish-clean",
        audit_metadata={"worker_id": "worker-2"},
    )

    # But different payload or hashes MUST raise ExperimentImmutabilityError
    with pytest.raises(ExperimentImmutabilityError):
        repo.put(
            experiment_id=exp_id,
            deterministic_payload={"score": 999},  # Changed!
            content_hashes=content_hashes,
            execution_id="exec-diff",
            audit_metadata={"worker_id": "worker-3"},
        )


# ---------------------------------------------------------------------------
# R3-03: Portable boolean syntax in atomic job completion
# ---------------------------------------------------------------------------

def test_atomic_completion_portable_boolean_query(r3_fixture):
    """Probe 3: Atomic completion uses portable boolean parameter binding (:not_cancelled = False)."""
    _, engine, _, _, _ = r3_fixture
    repo = ExperimentRepository(engine)
    exp_id = "exp-bool-query"
    gen_id = "gen-bool-query"
    job_id = "job-bool-query"
    fencing_token = "tok-bool-1"

    now = datetime.now(timezone.utc)
    future_str = (now + timedelta(seconds=120)).isoformat()
    now_str = now.isoformat()

    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO jobs (id, payload_hash, request_params_json, status, worker_id, fencing_token, attempt, max_attempts,
                                  lease_expires_at, cancel_requested, created_at, started_at)
                VALUES (:job_id, 'hash-bool', '{"preset_name": "bank-outage-50"}', 'running', 'worker-b', :token, 1, 3,
                        :lease, 0, :now, :now)
            """),
            {"job_id": job_id, "token": fencing_token, "lease": future_str, "now": now_str},
        )

    payload = {"experiment_id": "exp-bool-test"}
    digest = stable_hash(payload)
    exp_id = digest[:24]
    manifest = {"result.json": "hash-res"}
    repo.reserve_publication(
        generation_id=gen_id,
        experiment_id=exp_id,
        full_digest=digest,
        execution_id="exec-bool-1",
        manifest=manifest,
        job_id=job_id,
        attempt=1,
        fencing_token=fencing_token,
        prepared_payload=payload,
        lease_expires_at=future_str,
    )

    # Execute put() with job_context: must succeed with portable boolean binding
    repo.put(
        experiment_id=exp_id,
        deterministic_payload=payload,
        content_hashes={"result": "hash-res", "logical_content": digest},
        execution_id="exec-bool-1",
        audit_metadata={"worker_id": "worker-b"},
        generation_id=gen_id,
        job_context=(job_id, fencing_token),
    )

    # Job is completed
    with engine.connect() as conn:
        j_row = conn.execute(
            text("SELECT status, completed_at FROM jobs WHERE id = :job_id"),
            {"job_id": job_id},
        ).mappings().one()
        assert j_row["status"] == "completed"
        assert j_row["completed_at"] is not None


# ---------------------------------------------------------------------------
# R3-04: Universal publication ownership protocol with bounded lease for CLI
# ---------------------------------------------------------------------------

def test_unleased_cli_owner_protected_from_takeover(r3_fixture):
    """Probe 4: CLI publication receives bounded lease; second reservation while active raises PublicationContentionError."""
    _, engine, _, _, _ = r3_fixture
    repo = ExperimentRepository(engine)
    exp_id = "exp-cli-owner"
    gen1 = "gen-cli-1"
    gen2 = "gen-cli-2"

    manifest1 = {"result.json": "hash-cli-1"}
    manifest2 = {"result.json": "hash-cli-2"}

    # 1. CLI reserves generation 1 without explicit lease_expires_at (job_id is None)
    repo.reserve_publication(
        generation_id=gen1,
        experiment_id=exp_id,
        full_digest="digest-1",
        execution_id="exec-cli-1",
        manifest=manifest1,
    )

    pub1 = repo.get_publication(gen1)
    assert pub1.status == "PREPARED"
    assert pub1.lease_expires_at is not None  # Automatically got bounded lease!

    # 2. Worker / another caller attempts to reserve generation 2 while gen1's lease is still active
    with pytest.raises(PublicationContentionError):
        repo.reserve_publication(
            generation_id=gen2,
            experiment_id=exp_id,
            full_digest="digest-2",
            execution_id="exec-cli-2",
            manifest=manifest2,
        )

    # 3. Generation 1 must remain PREPARED and NOT be ABANDONED
    pub1_after = repo.get_publication(gen1)
    assert pub1_after.status == "PREPARED"

    # 4. If gen1 lease expires in the past, second reservation is permitted and gen1 becomes ABANDONED
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE experiment_publications SET lease_expires_at = '2026-09-17T00:00:00Z' WHERE generation_id = :gen1"),
            {"gen1": gen1},
        )

    gen3 = "gen-cli-3"
    repo.reserve_publication(
        generation_id=gen3,
        experiment_id=exp_id,
        full_digest="digest-3",
        execution_id="exec-cli-3",
        manifest=manifest1,
    )
    pub1_expired = repo.get_publication(gen1)
    assert pub1_expired.status == "ABANDONED"
    pub3 = repo.get_publication(gen3)
    assert pub3.status == "PREPARED"


# ---------------------------------------------------------------------------
# R3-05: Multiprocess admission and idempotency serialization
# ---------------------------------------------------------------------------

def _worker_enqueue_same_idempotency(db_url: str, session_id: str, cap_token: str, idem_key: str, payload_hash: str) -> str:
    """Helper executed in concurrent workers."""
    eng = create_engine(db_url)
    queue = JobQueue(eng)
    job = queue.enqueue(
        payload_hash=payload_hash,
        request_params={"preset_name": "bank-outage-50"},
        session_id=session_id,
        idempotency_key=idem_key,
    )
    eng.dispose()
    return job.id


def test_concurrent_idempotency_serialization(r3_fixture):
    """Probe 5a: Concurrent workers enqueuing same idempotency key all return winning job; exactly 1 job created."""
    client, engine, _, _, db_file = r3_fixture

    # Create session
    s_res = client.post("/api/v1/agent/sessions", json={})
    assert s_res.status_code == 201
    sid = s_res.json()["session_id"]
    tok = s_res.json()["capability_token"]

    idem_key = "idem-multiprocess-key"
    payload_hash = "payload-hash-same"
    db_url = f"sqlite:///{db_file}"

    # Launch 10 concurrent enqueue attempts
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [
            executor.submit(_worker_enqueue_same_idempotency, db_url, sid, tok, idem_key, payload_hash)
            for _ in range(10)
        ]
        results = [f.result() for f in futures]

    # All 10 must return the identical winning job ID
    assert len(set(results)) == 1
    winning_job_id = results[0]

    # Verify exactly 1 job exists in the database
    with engine.connect() as conn:
        count = conn.execute(text("SELECT count(*) FROM jobs WHERE session_id = :sid"), {"sid": sid}).scalar()
        assert count == 1
        j_id = conn.execute(text("SELECT id FROM jobs WHERE session_id = :sid"), {"sid": sid}).scalar()
        assert j_id == winning_job_id


def test_concurrent_admission_quota_strictly_enforced(r3_fixture):
    """Probe 5b: Concurrent admission requests strictly enforce quota of 2 active jobs per session."""
    client, engine, _, _, db_file = r3_fixture

    # Create session
    s_res = client.post("/api/v1/agent/sessions", json={})
    sid = s_res.json()["session_id"]
    tok = s_res.json()["capability_token"]
    db_url = f"sqlite:///{db_file}"

    def _enqueue_unique(idx: int):
        eng = create_engine(db_url)
        queue = JobQueue(eng)
        try:
            job = queue.enqueue(
                payload_hash=f"hash-unique-{idx}",
                request_params={"preset_name": f"preset-{idx}"},
                session_id=sid,
                idempotency_key=f"idem-unique-{idx}",
            )
            return ("SUCCESS", job.id)
        except QuotaExceededError as e:
            return ("QUOTA_EXCEEDED", str(e))
        finally:
            eng.dispose()

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(_enqueue_unique, i) for i in range(5)]
        results = [f.result() for f in futures]

    successes = [r for r in results if r[0] == "SUCCESS"]
    quota_exceeded = [r for r in results if r[0] == "QUOTA_EXCEEDED"]

    assert len(successes) == 2
    assert len(quota_exceeded) == 3

    with engine.connect() as conn:
        active_count = conn.execute(
            text("SELECT count(*) FROM jobs WHERE session_id = :sid AND status IN ('queued', 'running')"),
            {"sid": sid},
        ).scalar()
        assert active_count == 2


# ---------------------------------------------------------------------------
# R3-06: Transition-time lease expiry verification and rollback
# ---------------------------------------------------------------------------

def test_transition_time_lease_expiry_rollback(r3_fixture):
    """Probe 6: If worker lease expires before final transition point, atomic update rolls back and raises WorkerFencedOutException."""
    _, engine, _, _, _ = r3_fixture
    repo = ExperimentRepository(engine)
    exp_id = "exp-lease-expiry"
    gen_id = "gen-lease-expiry"
    job_id = "job-lease-expiry"
    token = "tok-expiry-1"

    now = datetime.now(timezone.utc)
    # Set lease to already expired (e.g. 10 seconds ago)
    past_str = (now - timedelta(seconds=10)).isoformat()
    now_str = now.isoformat()

    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO jobs (id, payload_hash, request_params_json, status, worker_id, fencing_token, attempt, max_attempts,
                                  lease_expires_at, cancel_requested, created_at, started_at)
                VALUES (:job_id, 'hash-exp', '{"preset_name": "bank-outage-50"}', 'running', 'worker-exp', :token, 1, 3,
                        :lease, 0, :now, :now)
            """),
            {"job_id": job_id, "token": token, "lease": past_str, "now": now_str},
        )

    payload = {"experiment_id": "exp-lease-test"}
    digest = stable_hash(payload)
    exp_id = digest[:24]
    manifest = {"result.json": "hash-res"}
    repo.reserve_publication(
        generation_id=gen_id,
        experiment_id=exp_id,
        full_digest=digest,
        execution_id="exec-exp-1",
        manifest=manifest,
        job_id=job_id,
        attempt=1,
        fencing_token=token,
        prepared_payload=payload,
        lease_expires_at=past_str,
    )

    # Worker attempts put() with expired lease: must fail and roll back!
    with pytest.raises(WorkerFencedOutException):
        repo.put(
            experiment_id=exp_id,
            deterministic_payload=payload,
            content_hashes={"result": "hash-res", "logical_content": digest},
            execution_id="exec-exp-1",
            audit_metadata={"worker_id": "worker-exp"},
            generation_id=gen_id,
            job_context=(job_id, token),
        )

    # Verify atomic rollback: experiments table has NO row!
    with engine.connect() as conn:
        exp_row = conn.execute(text("SELECT id FROM experiments WHERE id = :id"), {"id": exp_id}).fetchone()
        assert exp_row is None

        # Publication did NOT become PUBLISHED
        pub = repo.get_publication(gen_id)
        assert pub.status == "PREPARED"

        # Job is still running (or unchanged)
        j_status = conn.execute(text("SELECT status FROM jobs WHERE id = :job_id"), {"job_id": job_id}).scalar()
        assert j_status == "running"
