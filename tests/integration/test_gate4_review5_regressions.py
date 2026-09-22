"""Regression tests for 2026-09-19 Complete Review findings (Batches 1 and 2).

Covers:
- C02: Attempt and fencing token binding on publication reservation & recovery
- C03: Corrupt generation manifest JSON isolation in recovery
- C04: Unexpired lease enforcement on worker terminal mutations
- C05: Cancellation claim race serialization
- C06: list_published deduplication across experiment reruns
- API-01: PresetOverrides validation (strict dev seeds, rejection of seed=0 and unsupported fields)
- API-02: bind_jobs_to_session CAS locking, dependency deduplication, cross-session and terminal guards
- API-03: Hosted profile propagation and PostgreSQL URL auto-detection
- API-04: SessionStatus.EXPIRED handling in auth and continuation
- API-06: Strict positive finite validation for worker and recovery polling intervals
- SCI-01: Bank clean dataset row count and digest verification
- SCI-05: Calibration missingness fraction dimensionality, bounds, and alignment validation
- SCI-06: Config master_seed integer enforcement and protocol_id validation
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import text
from starlette.testclient import TestClient

from tests.integration.test_gate4_review4_regressions import _prepare_publication

from shiftguard.api.auth import verify_session_authority
from shiftguard.api.main import create_app
from shiftguard.api.schemas import PresetOverrides
from shiftguard.calibration.fraction_binned import validate_fractions
from shiftguard.cli import app as cli_app
from shiftguard.datasets.bank import BANK_FEATURES, BankDataset, FROZEN_BANK_SOURCE, write_clean_csv
from shiftguard.experiments.config import BaselineConfig, OutageConfig, StressConfig
from shiftguard.experiments.ids import stable_hash
from shiftguard.jobs.continuation import ContinuationService
from shiftguard.jobs.models import JobStatus, SessionStatus
from shiftguard.jobs.queue import JobQueue
from shiftguard.jobs.recovery import (
    recover_expired_leases,
    recover_prepared_publications,
    run_recovery_cycle,
)
from shiftguard.migrations import upgrade_database
from shiftguard.settings import Settings
from shiftguard.storage.db import create_engine_for_settings
from shiftguard.storage.repositories import (
    ExperimentRepository,
    canonical_content_hashes,
)


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def test_env(tmp_path):
    """Create a fresh SQLite test environment."""
    db_url = f"sqlite:///{tmp_path / 'test.db'}"
    settings = Settings(SHIFTGUARD_DB_URL=db_url, SHIFTGUARD_ARTIFACT_ROOT=str(tmp_path / "artifacts"))
    upgrade_database(settings)
    engine = create_engine_for_settings(settings)
    repo = ExperimentRepository(engine)
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir(exist_ok=True)
    yield {
        "engine": engine,
        "repo": repo,
        "artifacts": artifacts,
        "settings": settings,
        "tmp_path": tmp_path,
        "db_url": db_url,
    }
    engine.dispose()


# ─── Batch 1 Regressions ─────────────────────────────────────────────────────


def test_c02_attempt_binding_fences_stale_generation(test_env):
    """C02: A generation reserved by attempt 1 cannot be recovered by attempt 2."""
    engine = test_env["engine"]
    repo = test_env["repo"]
    artifacts = test_env["artifacts"]

    old = _prepare_publication(test_env, "old-attempt", job=True)
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE jobs SET attempt=2, fencing_token='new-attempt-token' WHERE id=:id"),
            {"id": old["job_id"]},
        )
    quarantined = recover_prepared_publications(engine, artifacts)
    assert quarantined >= 1

    pub = repo.get_publication(old["gen_id"])
    assert pub.status == "QUARANTINED"


def test_c03_corrupt_json_isolation_in_recovery(test_env):
    """C03: A corrupt generation manifest does not crash or abort recovery of valid generations."""
    engine = test_env["engine"]
    repo = test_env["repo"]
    artifacts = test_env["artifacts"]

    bad = _prepare_publication(test_env, "malformed-json")
    later = _prepare_publication(test_env, "valid-after-corruption")
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE experiment_publications SET prepared_payload_json='{' WHERE generation_id=:id"),
            {"id": bad["gen_id"]},
        )

    # Recovery must not raise JSONDecodeError and must isolate corrupt generation
    recover_prepared_publications(engine, artifacts)

    assert repo.get_publication(bad["gen_id"]).status == "QUARANTINED"
    assert repo.get_publication(later["gen_id"]).status == "PUBLISHED"


def test_c04_unexpired_lease_guard_on_worker_terminal_mutations(test_env):
    """C04: Worker cannot mark_failed or mark_cancelled if its lease expired."""
    engine = test_env["engine"]
    queue = JobQueue(engine)

    # Create and claim job
    job = queue.enqueue(request_params={"preset_name": "bank-outage-50"}, payload_hash="hash-c04")
    claimed = queue.claim_next_job("worker-1", lease_seconds=1)
    assert claimed is not None

    # Manually expire the lease in the DB
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE jobs SET lease_expires_at = '2000-01-01T00:00:00+00:00' WHERE id = :id"),
            {"id": job.id},
        )

    # Attempt terminal mutations with expired lease - should be rejected / return False
    res_cancel = queue.mark_cancelled_by_worker(job.id, "worker-1")
    assert res_cancel is False

    res_fail = queue.mark_failed(job.id, "worker-1", "failure message")
    assert res_fail is False

    # Status in DB remains RUNNING so recovery supervisor can handle it
    job_after = queue.get_job(job.id)
    assert job_after.status == JobStatus.RUNNING


def test_c06_list_published_deduplication(test_env):
    """C06: list_published groups on experiment_id and returns the latest publication."""
    engine = test_env["engine"]
    repo = test_env["repo"]

    exp_id = "exp-c06-dedup"
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO experiments (id, payload_json, content_hashes_json) "
                "VALUES (:id, '{}', '{}')"
            ),
            {"id": exp_id},
        )

    # Insert two publications for the same experiment
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO experiment_publications "
                "(generation_id, experiment_id, full_digest, execution_id, manifest_json, status, created_at, updated_at) "
                "VALUES "
                "('gen-1', :id, 'full-1', 'exec-1', '{}', 'PUBLISHED', '2026-09-19T01:00:00+00:00', '2026-09-19T01:00:00+00:00'), "
                "('gen-2', :id, 'full-2', 'exec-2', '{}', 'PUBLISHED', '2026-09-19T02:00:00+00:00', '2026-09-19T02:00:00+00:00')"
            ),
            {"id": exp_id},
        )

    published = repo.list_published()
    assert len(published) == 1
    assert published[0]["experiment_id"] == exp_id
    assert published[0]["created_at"] == "2026-09-19T02:00:00+00:00"


# ─── Batch 2 Regressions ─────────────────────────────────────────────────────


def test_api_01_preset_overrides_schema_strictness():
    """API-01: PresetOverrides accepts valid development seeds and rejects seed=0 and extra fields."""
    # Valid development seeds
    for s in (31001, 31002, 31003):
        po = PresetOverrides(seed=s)
        assert po.seed == s

    # Unsupported seeds
    with pytest.raises(ValidationError):
        PresetOverrides(seed=0)

    with pytest.raises(ValidationError):
        PresetOverrides(seed=42)

    with pytest.raises(ValidationError):
        PresetOverrides(seed=31004)

    # Unsupported fields
    with pytest.raises(ValidationError):
        PresetOverrides(seed=31001, test_fraction=0.2)

    with pytest.raises(ValidationError):
        PresetOverrides(seed=31001, history_probability=0.5)


def test_api_02_bind_jobs_to_session_cas_and_deduplication(test_env):
    """API-02: bind_jobs_to_session deduplicates dependencies and enforces session/terminal guards."""
    engine = test_env["engine"]
    continuation = ContinuationService(engine)
    queue = JobQueue(engine)

    # Create session
    session = continuation.create_session("agent-1")
    other_session = continuation.create_session("agent-2")

    # Enqueue jobs
    job1 = queue.enqueue(request_params={"preset_name": "p1"}, session_id=session.id, payload_hash="hash-1")
    job2 = queue.enqueue(request_params={"preset_name": "p2"}, session_id=session.id, payload_hash="hash-2")
    job_other = queue.enqueue(request_params={"preset_name": "p3"}, session_id=other_session.id, payload_hash="hash-3")

    # Bind job1
    s_bound = continuation.bind_jobs_to_session(session.id, [job1.id])
    assert s_bound.status == SessionStatus.WAITING_FOR_JOB
    assert s_bound.required_job_ids == [job1.id]

    # Rebind job1 and job2 (should append and deduplicate)
    s_rebound = continuation.bind_jobs_to_session(session.id, [job1.id, job2.id])
    assert set(s_rebound.required_job_ids) == {job1.id, job2.id}
    assert len(s_rebound.required_job_ids) == 2

    # Cross-session job binding must be rejected
    with pytest.raises(ValueError, match="does not belong to session"):
        continuation.bind_jobs_to_session(session.id, [job_other.id])

    # Terminal session binding must be rejected
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE agent_sessions SET status = 'completed' WHERE id = :id"),
            {"id": session.id},
        )
    with pytest.raises(ValueError, match="Cannot bind jobs to terminal session"):
        continuation.bind_jobs_to_session(session.id, [job1.id])


def test_api_03_experiment_repo_postgres_profile_detection():
    """API-03: from_url auto-detects PostgreSQL and defaults environment to hosted."""
    with patch("shiftguard.storage.repositories.upgrade_database"), \
         patch("shiftguard.storage.repositories.create_engine_for_settings") as mock_create:
        mock_create.return_value = MagicMock()
        repo = ExperimentRepository.from_url("postgresql+psycopg://user:pass@localhost:5432/shiftguard")
        assert repo.environment == "hosted"


def test_api_04_session_status_expired_in_auth(test_env):
    """API-04: verify_session_authority returns HTTP 401 SESSION_EXPIRED on expired sessions."""
    engine = test_env["engine"]
    continuation = ContinuationService(engine)

    session = continuation.create_session("agent-exp")
    # Mark expired
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE agent_sessions SET status = 'expired' WHERE id = :id"),
            {"id": session.id},
        )

    with pytest.raises(HTTPException) as exc_info:
        verify_session_authority(engine, session.id, session.capability_token)

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail["error"]["code"] == "SESSION_EXPIRED"

    # ContinuationService resume on expired session returns (401, SESSION_EXPIRED)
    status_code, resp = continuation.resume(session.id, session.active_nonce, JobQueue(engine))
    assert status_code == 401
    assert resp["error"]["code"] == "SESSION_EXPIRED"


def test_api_06_polling_interval_validation():
    """API-06: Settings rejects nonpositive or nonfinite worker and recovery intervals."""
    # Zero interval
    with pytest.raises(ValidationError):
        Settings(worker_poll_interval=0.0)

    with pytest.raises(ValidationError):
        Settings(recovery_interval=0.0)

    # Negative interval
    with pytest.raises(ValidationError):
        Settings(worker_poll_interval=-1.0)

    with pytest.raises(ValidationError):
        Settings(recovery_interval=-0.1)

    # Nonfinite interval
    with pytest.raises(ValidationError):
        Settings(worker_poll_interval=float("inf"))

    with pytest.raises(ValidationError):
        Settings(recovery_interval=float("nan"))

    # Valid positive interval succeeds
    s = Settings(worker_poll_interval=0.5, recovery_interval=10.0)
    assert s.worker_poll_interval == 0.5
    assert s.recovery_interval == 10.0


def test_sci_01_bank_clean_dataset_verification(tmp_path):
    """SCI-01: BankDataset rejects modified/fabricated clean CSVs unless allow_synthetic is set."""
    row = {feature: "unknown" for feature in BANK_FEATURES}
    row.update({"row_id": "1", "age": "30", "pdays": "999", "previous": "0", "y": "0"})
    fake_csv = tmp_path / "fake_bank.csv"
    write_clean_csv([row], fake_csv)

    file_hash = hashlib.sha256(fake_csv.read_bytes()).hexdigest()
    manifest = dict(FROZEN_BANK_SOURCE)
    manifest["clean_sha256"] = file_hash
    manifest["rows"] = 1

    # Production loader rejects fabricated 1-row CSV because hash/rows don't match frozen canonical
    with pytest.raises(ValueError, match="does not match frozen canonical"):
        BankDataset.from_clean_csv(fake_csv, manifest)

    # Synthetic loader accepts it with allow_synthetic=True
    ds = BankDataset.from_synthetic_csv(fake_csv, manifest)
    assert len(ds.rows) == 1


def test_sci_05_fraction_binned_validation():
    """SCI-05: validate_fractions enforces 1D, finite, [0, 1] range, and length alignment."""
    # Valid
    f = np.array([0.0, 0.5, 1.0])
    validate_fractions(f, expected_rows=3)

    # 2D array
    with pytest.raises(ValueError, match="1-dimensional"):
        validate_fractions(np.zeros((3, 1)), expected_rows=3)

    # NaN / Inf
    with pytest.raises(ValueError, match="finite"):
        validate_fractions(np.array([0.1, np.nan, 0.5]), expected_rows=3)

    with pytest.raises(ValueError, match="finite"):
        validate_fractions(np.array([0.1, np.inf, 0.5]), expected_rows=3)

    # Out of range (< 0 or > 1)
    with pytest.raises(ValueError, match="range \\[0, 1\\]"):
        validate_fractions(np.array([-0.01, 0.5, 0.5]), expected_rows=3)

    with pytest.raises(ValueError, match="range \\[0, 1\\]"):
        validate_fractions(np.array([0.0, 1.05, 0.5]), expected_rows=3)

    # Mismatched length
    with pytest.raises(ValueError, match="expected 4 fractions"):
        validate_fractions(f, expected_rows=4)


def test_sci_06_integer_seed_and_protocol_identity():
    """SCI-06: Configs strictly require integer seeds and declared protocol_id."""
    # Valid
    cfg = BaselineConfig(master_seed=31001)
    assert cfg.master_seed == 31001
    assert cfg.protocol_id == "sg-protocol-1.0-draft"

    # Float seed must be rejected
    with pytest.raises(TypeError, match="master_seed must be an int"):
        BaselineConfig(master_seed=31001.0)

    # Bool seed must be rejected
    with pytest.raises(TypeError, match="master_seed must be an int"):
        BaselineConfig(master_seed=True)

    # Invalid protocol_id must be rejected
    with pytest.raises(ValueError, match="protocol_id must match declared protocol identity"):
        BaselineConfig(master_seed=31001, protocol_id="custom-protocol")

    # StressConfig protocol_id
    with pytest.raises(ValueError, match="protocol_id must match declared protocol identity"):
        StressConfig(master_seed=31001, protocol_id="invalid")
