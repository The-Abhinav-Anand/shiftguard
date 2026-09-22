"""Comprehensive regression tests for all 6 findings and 7 failure probes from Gate 4 Review #2.

Verifies:
- R2-01: Session authority enforcement (rejection of uncredentialed read, cancel, and submissions).
- R2-02: Publication ownership serialization and prevention of abandoned generation resurrection.
- R2-03: Recovery safety (active running job protection, experiment/audit record reconstruction, quarantine on missing metadata).
- R2-04: Fenced atomic completion rollback on cancellation / fencing token loss.
- R2-05: Strict admission quota of 2 active jobs per session.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
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
from shiftguard.jobs.queue import JobQueue
from shiftguard.jobs.recovery import recover_prepared_publications
from shiftguard.migrations import upgrade_database
from shiftguard.settings import Settings
from shiftguard.storage.repositories import ExperimentRepository


@pytest.fixture
def r2_fixture(tmp_path):
    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir(parents=True, exist_ok=True)
    db_file = tmp_path / "r2_regressions.db"
    settings = Settings(
        SHIFTGUARD_DB_URL=f"sqlite:///{db_file}",
        SHIFTGUARD_ARTIFACT_ROOT=str(artifact_root),
    )
    upgrade_database(settings)
    app = create_app(settings)
    engine = create_engine(f"sqlite:///{db_file}")
    with TestClient(app) as client:
        yield client, engine, artifact_root, settings
    engine.dispose()


# ---------------------------------------------------------------------------
# R2-01: Session Authority Enforcement
# ---------------------------------------------------------------------------

def test_job_read_without_session_rejected(r2_fixture):
    """Probe 1: Reading session-owned job without credentials returns 401 MISSING_SESSION_CREDENTIALS."""
    client, engine, _, _ = r2_fixture

    # 1. Create a session
    s_res = client.post("/api/v1/agent/sessions", json={})
    assert s_res.status_code == 201
    s_data = s_res.json()
    session_id = s_data["session_id"]
    cap_token = s_data["capability_token"]

    # 2. Submit a job with valid session credentials
    sub_res = client.post(
        "/api/v1/experiments",
        json={"preset_name": "bank-outage-50"},
        headers={"X-Session-ID": session_id, "X-Session-Token": cap_token},
    )
    assert sub_res.status_code == 202
    job_id = sub_res.json()["job_id"]

    # 3. Read without credentials -> 401
    unauth_res = client.get(f"/api/v1/jobs/{job_id}")
    assert unauth_res.status_code == 401
    assert unauth_res.json()["error"]["code"] == "MISSING_SESSION_CREDENTIALS"

    # 4. Read with valid credentials -> 200
    auth_res = client.get(
        f"/api/v1/jobs/{job_id}",
        headers={"X-Session-ID": session_id, "X-Session-Token": cap_token},
    )
    assert auth_res.status_code == 200
    assert auth_res.json()["job_id"] == job_id


def test_job_cancel_without_session_rejected(r2_fixture):
    """Probe 2: Cancelling session-owned job without credentials returns 401; wrong session returns 403."""
    client, engine, _, _ = r2_fixture

    # 1. Create session A and submit job
    s_res_a = client.post("/api/v1/agent/sessions", json={})
    sid_a = s_res_a.json()["session_id"]
    tok_a = s_res_a.json()["capability_token"]

    sub_res = client.post(
        "/api/v1/experiments",
        json={"preset_name": "bank-outage-50"},
        headers={"X-Session-ID": sid_a, "X-Session-Token": tok_a},
    )
    job_id = sub_res.json()["job_id"]

    # 2. Anonymous cancellation -> 401
    anon_res = client.post(f"/api/v1/jobs/{job_id}/cancel")
    assert anon_res.status_code == 401
    assert anon_res.json()["error"]["code"] == "MISSING_SESSION_CREDENTIALS"

    # 3. Cancel with session B -> 403
    s_res_b = client.post("/api/v1/agent/sessions", json={})
    sid_b = s_res_b.json()["session_id"]
    tok_b = s_res_b.json()["capability_token"]

    cross_res = client.post(
        f"/api/v1/jobs/{job_id}/cancel",
        headers={"X-Session-ID": sid_b, "X-Session-Token": tok_b},
    )
    assert cross_res.status_code == 403
    assert cross_res.json()["error"]["code"] == "CROSS_SESSION_ACCESS_DENIED"

    # 4. Cancel with owner session A -> 202
    owner_res = client.post(
        f"/api/v1/jobs/{job_id}/cancel",
        headers={"X-Session-ID": sid_a, "X-Session-Token": tok_a},
    )
    assert owner_res.status_code == 202
    assert owner_res.json()["status"] == "cancelled"


def test_six_sessionless_submissions_rejected(r2_fixture):
    """Probe 3: 6 anonymous submissions without session credentials are all rejected with 401."""
    client, _, _, _ = r2_fixture

    responses = []
    for _ in range(6):
        res = client.post("/api/v1/experiments", json={"preset_name": "bank-outage-50"})
        responses.append(res.status_code)

    assert responses == [401, 401, 401, 401, 401, 401]


# ---------------------------------------------------------------------------
# R2-02: Publication Ownership & Contention
# ---------------------------------------------------------------------------

def test_reserve_second_generation_while_first_live_fails(r2_fixture):
    """Probe 4: Reserving a new generation while an active live job holds the lease raises PublicationContentionError."""
    _, engine, _, _ = r2_fixture
    repo = ExperimentRepository(engine)
    exp_id = "exp-contention-test"
    manifest = {"metrics.json": "hash-abc"}

    # 1. Simulate job 1 active and running
    now = datetime.now(timezone.utc)
    now_str = now.isoformat()
    future_str = (now + timedelta(seconds=120)).isoformat()

    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO jobs (id, payload_hash, request_params_json, status, worker_id, fencing_token, attempt, max_attempts,
                                  lease_expires_at, cancel_requested, created_at, started_at)
                VALUES ('job-live-1', 'dummyhash', '{"preset_name": "bank-outage-50"}', 'running', 'worker-1', 'tok-1', 1, 3,
                        :lease, 0, :now, :now)
            """),
            {"lease": future_str, "now": now_str},
        )

    # 2. Job 1 reserves generation 1
    gen1 = "gen-owner-1"
    repo.reserve_publication(
        generation_id=gen1,
        experiment_id=exp_id,
        full_digest="digest-1",
        execution_id="exec-1",
        manifest=manifest,
        job_id="job-live-1",
        lease_expires_at=future_str,
    )

    pub1 = repo.get_publication(gen1)
    assert pub1.status == "PREPARED"

    # 3. Competing generation 2 tries to reserve while job 1 is live -> raises PublicationContentionError
    gen2 = "gen-competing-2"
    with pytest.raises(PublicationContentionError):
        repo.reserve_publication(
            generation_id=gen2,
            experiment_id=exp_id,
            full_digest="digest-2",
            execution_id="exec-2",
            manifest=manifest,
            job_id="job-other-2",
            lease_expires_at=future_str,
        )

    # 4. Generation 1 must remain PREPARED and not ABANDONED
    pub1_after = repo.get_publication(gen1)
    assert pub1_after.status == "PREPARED"


def test_abandoned_generation_cannot_publish(r2_fixture):
    """Probe 5: Calling put() with an ABANDONED generation raises PublicationLostOwnershipError."""
    _, engine, _, _ = r2_fixture
    repo = ExperimentRepository(engine)
    exp_id = "exp-abandoned-test"
    manifest = {"metrics.json": "hash-abc"}

    # 1. Reserve generation 1 with no active running job (lease expired)
    gen1 = "gen-dead-1"
    repo.reserve_publication(
        generation_id=gen1,
        experiment_id=exp_id,
        full_digest="digest-1",
        execution_id="exec-1",
        manifest=manifest,
        lease_expires_at="2026-09-17T00:00:00Z",
    )

    # 2. Reserve generation 2 (since gen1 has no live job lease, gen1 becomes ABANDONED)
    gen2 = "gen-alive-2"
    repo.reserve_publication(
        generation_id=gen2,
        experiment_id=exp_id,
        full_digest="digest-2",
        execution_id="exec-2",
        manifest=manifest,
    )

    pub1 = repo.get_publication(gen1)
    assert pub1.status == "ABANDONED"

    # 3. Stale worker for gen1 tries to publish -> must raise PublicationLostOwnershipError
    with pytest.raises(PublicationLostOwnershipError):
        repo.put(
            experiment_id=exp_id,
            deterministic_payload={"data": 123},
            content_hashes=manifest,
            execution_id="exec-1",
            audit_metadata={"worker": "dead"},
            generation_id=gen1,
        )


# ---------------------------------------------------------------------------
# R2-03: Recovery Safety & Running Job Protection
# ---------------------------------------------------------------------------

def test_recovery_preserves_live_running_job(r2_fixture):
    """Probe 6: Recovery protects live running jobs and leaves their PREPARED generation and staging intact."""
    _, engine, artifact_root, _ = r2_fixture
    exp_id = "exp-live-running"
    gen_id = "gen-live-running"
    job_id = "job-live-running"

    now = datetime.now(timezone.utc)
    now_str = now.isoformat()
    future_str = (now + timedelta(seconds=300)).isoformat()

    # Create running job with valid lease
    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO jobs (id, payload_hash, request_params_json, status, worker_id, fencing_token, attempt, max_attempts,
                                  lease_expires_at, cancel_requested, created_at, started_at)
                VALUES (:job_id, 'dummyhash', '{"preset_name": "bank-outage-50"}', 'running', 'worker-live', 'tok-live', 1, 3,
                        :lease, 0, :now, :now)
            """),
            {"job_id": job_id, "lease": future_str, "now": now_str},
        )

    # Create PREPARED publication with matching job_id
    manifest = {"output.json": "somehash"}
    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO experiment_publications (
                    generation_id, experiment_id, status, full_digest, execution_id,
                    manifest_json, job_id, lease_expires_at, created_at, updated_at
                )
                VALUES (
                    :gen_id, :exp_id, 'PREPARED', 'digest', 'exec-live',
                    :manifest, :job_id, :lease, :now, :now
                )
            """),
            {"gen_id": gen_id, "exp_id": exp_id, "manifest": json.dumps(manifest), "job_id": job_id, "lease": future_str, "now": now_str},
        )

    # Create live staging directory
    staging_dir = artifact_root / ".staging" / gen_id
    staging_dir.mkdir(parents=True, exist_ok=True)
    (staging_dir / "output.json").write_text("in-progress")

    # Run recovery
    recover_prepared_publications(engine, artifact_root)

    # Verify: publication is still PREPARED, staging exists, job is still running
    repo = ExperimentRepository(engine)
    pub = repo.get_publication(gen_id)
    assert pub.status == "PREPARED"
    assert staging_dir.exists()

    with engine.connect() as conn:
        j_status = conn.execute(text("SELECT status FROM jobs WHERE id = :job_id"), {"job_id": job_id}).scalar()
        assert j_status == "running"


def test_recovery_reconstructs_experiment_records(r2_fixture):
    """Probe 7: When artifacts on disk match manifest after crash, recovery reconstructs experiments and executions rows atomically."""
    _, engine, artifact_root, _ = r2_fixture
    payload = {"metric": 0.99}
    full_digest = stable_hash(payload)
    exp_id = full_digest[:24]
    gen_id = "gen-reconstruct"
    job_id = "job-crashed"

    now_str = utc_now_str()
    expired_str = "2026-09-17T00:00:00Z"

    # Files on disk in final destination
    exp_dir = artifact_root / exp_id
    exp_dir.mkdir(parents=True, exist_ok=True)
    f_content = b'{"metric": 0.99}'
    (exp_dir / "metrics.json").write_bytes(f_content)
    f_hash = hashlib.sha256(f_content).hexdigest()
    manifest = {"metrics.json": f_hash}

    audit = {"worker_id": "worker-crashed", "host": "test-host"}

    # Insert dead job and prepared publication with metadata
    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO jobs (id, payload_hash, request_params_json, status, worker_id, fencing_token, attempt, max_attempts,
                                  lease_expires_at, cancel_requested, created_at, started_at)
                VALUES (:job_id, 'dummyhash', '{"preset_name": "bank-outage-50"}', 'running', 'worker-crashed', 'tok-crashed', 1, 3,
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
                    :gen_id, :exp_id, 'PREPARED', :full_digest, 'exec-crashed-1',
                    :manifest, :job_id, :lease, :payload, :audit, :now, :now
                )
            """),
            {
                "gen_id": gen_id,
                "exp_id": exp_id,
                "full_digest": full_digest,
                "manifest": json.dumps(manifest),
                "job_id": job_id,
                "lease": expired_str,
                "payload": json.dumps(payload),
                "audit": json.dumps(audit),
                "now": expired_str,
            },
        )

    # Run crash recovery
    recovered_count = recover_prepared_publications(engine, artifact_root)
    assert recovered_count == 1

    repo = ExperimentRepository(engine)
    pub = repo.get_publication(gen_id)
    assert pub.status == "PUBLISHED"

    # Both experiment and execution records were reconstructed!
    published_exp = repo.get_published(exp_id)
    assert published_exp is not None
    exp_rec, pub_rec = published_exp
    assert exp_rec.experiment_id == exp_id
    assert exp_rec.deterministic_payload == payload
    assert pub_rec.status == "PUBLISHED"

    with engine.connect() as conn:
        exec_row = conn.execute(
            text("SELECT audit_json FROM experiment_executions WHERE execution_id = 'exec-crashed-1'")
        ).scalar()
        assert exec_row is not None
        assert json.loads(exec_row) == audit

        # Job is marked completed
        job_status = conn.execute(text("SELECT status FROM jobs WHERE id = :job_id"), {"job_id": job_id}).scalar()
        assert job_status == "completed"


def test_recovery_quarantines_when_metadata_missing(r2_fixture):
    """Probe 7 (safety): If files exist but prepared metadata is missing, publication is QUARANTINED (no ghost experiment)."""
    _, engine, artifact_root, _ = r2_fixture
    exp_id = "exp-missing-meta"
    gen_id = "gen-missing-meta"

    exp_dir = artifact_root / exp_id
    exp_dir.mkdir(parents=True, exist_ok=True)
    f_content = b'{"data": 1}'
    (exp_dir / "data.json").write_bytes(f_content)
    manifest = {"data.json": hashlib.sha256(f_content).hexdigest()}

    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO experiment_publications (
                    generation_id, experiment_id, status, full_digest, execution_id,
                    manifest_json, job_id, lease_expires_at, prepared_payload_json,
                    prepared_audit_json, created_at, updated_at
                )
                VALUES (
                    :gen_id, :exp_id, 'PREPARED', 'digest', 'exec-no-meta',
                    :manifest, 'job-expired', '2026-09-17T00:00:00Z', NULL, NULL,
                    '2026-09-17T00:00:00Z', '2026-09-17T00:00:00Z'
                )
            """),
            {"gen_id": gen_id, "exp_id": exp_id, "manifest": json.dumps(manifest)},
        )

    recover_prepared_publications(engine, artifact_root)

    repo = ExperimentRepository(engine)
    pub = repo.get_publication(gen_id)
    assert pub.status == "QUARANTINED"
    assert repo.get_published(exp_id) is None


# ---------------------------------------------------------------------------
# R2-04: Fenced Atomic Completion
# ---------------------------------------------------------------------------

def test_job_completion_fenced_with_cancellation_race(r2_fixture):
    """R2-04: If job cancellation is requested before completion, repository.put() raises WorkerCancelledException and rolls back."""
    _, engine, _, _ = r2_fixture
    repo = ExperimentRepository(engine)
    exp_id = "exp-fence-cancel"
    gen_id = "gen-fence-cancel"
    job_id = "job-fence-cancel"
    fencing_token = "tok-fence"

    now_str = utc_now_str()
    future_str = (datetime.now(timezone.utc) + timedelta(seconds=120)).isoformat()

    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO jobs (id, payload_hash, request_params_json, status, worker_id, fencing_token, attempt, max_attempts,
                                  lease_expires_at, cancel_requested, created_at, started_at)
                VALUES (:job_id, 'dummyhash', '{"preset_name": "bank-outage-50"}', 'running', 'worker-1', :token, 1, 3,
                        :lease, 1, :now, :now)
            """),
            {"job_id": job_id, "token": fencing_token, "lease": future_str, "now": now_str},
        )

    payload = {"x": 1}
    digest = stable_hash(payload)
    exp_id = digest[:24]
    manifest = {"config.json": "hash-1"}
    repo.reserve_publication(
        generation_id=gen_id,
        experiment_id=exp_id,
        full_digest=digest,
        execution_id="exec-fence",
        manifest=manifest,
        job_id=job_id,
        attempt=1,
        fencing_token=fencing_token,
        prepared_payload=payload,
        lease_expires_at=future_str,
    )

    # Worker attempts put() with job_context: cancel_requested is 1!
    with pytest.raises(WorkerCancelledException):
        repo.put(
            experiment_id=exp_id,
            deterministic_payload=payload,
            content_hashes={"config.json": "hash-1", "logical_content": digest},
            execution_id="exec-fence",
            audit_metadata={"w": "1"},
            generation_id=gen_id,
            job_context=(job_id, fencing_token),
        )

    # Verify atomic rollback: experiments table has NO row!
    with engine.connect() as conn:
        exp_row = conn.execute(text("SELECT id FROM experiments WHERE id = :id"), {"id": exp_id}).fetchone()
        assert exp_row is None

        # Publication did NOT become PUBLISHED
        pub = repo.get_publication(gen_id)
        assert pub.status == "PREPARED"


# ---------------------------------------------------------------------------
# R2-05: Admission Quota Enforcement
# ---------------------------------------------------------------------------

def test_concurrent_admission_quota_strictly_two(r2_fixture):
    """R2-05: Session concurrency quota strictly enforces max 2 active jobs and rejects the 3rd with 429."""
    client, _, _, _ = r2_fixture

    # 1. Create a session
    s_res = client.post("/api/v1/agent/sessions", json={})
    sid = s_res.json()["session_id"]
    token = s_res.json()["capability_token"]
    headers = {"X-Session-ID": sid, "X-Session-Token": token}

    # 2. Submit job 1 -> 202
    res1 = client.post("/api/v1/experiments", json={"preset_name": "bank-outage-50"}, headers=headers)
    assert res1.status_code == 202

    # 3. Submit job 2 -> 202
    res2 = client.post("/api/v1/experiments", json={"preset_name": "bank-outage-50"}, headers=headers)
    assert res2.status_code == 202

    # 4. Submit job 3 under same session -> 429 SESSION_QUOTA_EXCEEDED
    res3 = client.post("/api/v1/experiments", json={"preset_name": "bank-outage-50"}, headers=headers)
    assert res3.status_code == 429
    assert res3.json()["error"]["code"] == "SESSION_QUOTA_EXCEEDED"

    # 5. Cancel one of the active jobs
    j1_id = res1.json()["job_id"]
    c_res = client.post(f"/api/v1/jobs/{j1_id}/cancel", headers=headers)
    assert c_res.status_code == 202

    # 6. Now submitting a new job should succeed with 202
    res4 = client.post("/api/v1/experiments", json={"preset_name": "bank-outage-50"}, headers=headers)
    assert res4.status_code == 202
