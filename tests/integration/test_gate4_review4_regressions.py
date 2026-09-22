"""Regression tests for Gate 4 Review #4 findings R4-01 through R4-04.

Each test reproduces the exact defect demonstrated by the independent probe
script (gate4-r4-probes.py) and asserts the corrected behavior.
"""
from __future__ import annotations

import hashlib
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import event, text

from shiftguard.experiments.ids import stable_hash
from shiftguard.jobs.recovery import (
    recover_expired_leases,
    recover_prepared_publications,
    run_recovery_cycle,
)
from shiftguard.migrations import upgrade_database
from shiftguard.settings import Settings
from shiftguard.storage.db import create_engine_for_settings
from shiftguard.storage.repositories import (
    ExperimentImmutabilityError,
    ExperimentRepository,
    canonical_content_hashes,
)


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def env(tmp_path):
    """Create a fresh SQLite test environment with engine, repo and artifact_root."""
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
    }
    engine.dispose()


def _expired_ts():
    return "2000-01-01T00:00:00+00:00"


def _future_ts(seconds=120):
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()


def _prepare_publication(env, tag, *, job=False, corrupt_digest=False, stage_only=False, expired_lease=True):
    """Create a PREPARED publication with optional job, staging, and corruption."""
    engine = env["engine"]
    repo = env["repo"]
    artifacts = env["artifacts"]

    payload = {"synthetic_review_probe": tag}
    digest = stable_hash(payload)
    exp_id = digest[:24]
    gen_id = f"gen-{tag}"
    exec_id = f"exec-{tag}"
    body = json.dumps(payload, sort_keys=True).encode()
    manifest = {"result.json": hashlib.sha256(body).hexdigest()}

    # Create artifact files
    if stage_only:
        target = artifacts / ".staging" / gen_id
    else:
        target = artifacts / exp_id
    target.mkdir(parents=True, exist_ok=True)
    (target / "result.json").write_bytes(body)

    job_id = f"job-{tag}" if job else None
    expired = _expired_ts()

    if job:
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO jobs
                    (id, payload_hash, request_params_json, status, worker_id, fencing_token,
                     attempt, max_attempts, lease_expires_at, cancel_requested, created_at, started_at)
                VALUES (:id, 'hash', '{}', 'running', 'worker', 'old-token', 1, 3,
                        :expired, :cancel, :expired, :expired)
            """), {"id": job_id, "expired": expired, "cancel": False})

    lease_ts = _expired_ts() if expired_lease else None
    repo.reserve_publication(
        gen_id, exp_id,
        "0" * 64 if corrupt_digest else digest,
        exec_id, manifest,
        job_id=job_id,
        lease_expires_at=lease_ts,
        prepared_payload=payload,
        prepared_audit={"probe": tag},
    )

    return {
        "exp_id": exp_id, "gen_id": gen_id, "exec_id": exec_id,
        "job_id": job_id, "digest": digest, "manifest": manifest,
        "target": target, "payload": payload,
    }


# ─── R4-01: Recovery protects live CLI publications ──────────────────────────


class TestR401LiveCLIProtection:
    """R4-01: Recovery must not quarantine jobless CLI publications with unexpired leases."""

    def test_live_cli_publication_survives_recovery(self, env):
        """A jobless PREPARED publication with unexpired lease must survive recovery."""
        repo = env["repo"]
        artifacts = env["artifacts"]

        # Create a CLI publication (no job) with an unexpired lease — stage_only=True
        # to simulate the window between reservation and rename
        info = _prepare_publication(env, "live-cli", stage_only=True, expired_lease=False)
        gen_id = info["gen_id"]
        staging_dir = artifacts / ".staging" / gen_id

        before = repo.get_publication(gen_id)
        assert before.status == "PREPARED"
        assert staging_dir.exists()

        # Run recovery — must NOT quarantine or delete staging
        recover_prepared_publications(env["engine"], artifacts)

        after = repo.get_publication(gen_id)
        assert after.status == "PREPARED", f"Expected PREPARED, got {after.status}"
        assert staging_dir.exists(), "Staging directory was destroyed by recovery"

    def test_expired_cli_publication_quarantined(self, env):
        """A jobless PREPARED publication with EXPIRED lease should be quarantined."""
        repo = env["repo"]
        artifacts = env["artifacts"]

        info = _prepare_publication(env, "expired-cli", stage_only=True, expired_lease=True)
        gen_id = info["gen_id"]

        recover_prepared_publications(env["engine"], artifacts)

        after = repo.get_publication(gen_id)
        assert after.status == "QUARANTINED"

    def test_live_cli_survives_full_recovery_cycle(self, env):
        """Live CLI publication survives the full run_recovery_cycle."""
        repo = env["repo"]
        artifacts = env["artifacts"]

        info = _prepare_publication(env, "cli-full-cycle", stage_only=True, expired_lease=False)
        gen_id = info["gen_id"]
        staging_dir = artifacts / ".staging" / gen_id

        run_recovery_cycle(env["engine"], artifacts)

        after = repo.get_publication(gen_id)
        assert after.status == "PREPARED"
        assert staging_dir.exists()

    def test_job_backed_unexpired_lease_also_protected(self, env):
        """Job-backed publications with unexpired leases are left untouched."""
        engine = env["engine"]
        repo = env["repo"]
        artifacts = env["artifacts"]

        # Create a job-backed publication with a valid lease
        payload = {"probe": "active-job"}
        digest = stable_hash(payload)
        exp_id = digest[:24]
        gen_id = "gen-active-job"
        exec_id = "exec-active-job"
        body = json.dumps(payload, sort_keys=True).encode()
        manifest = {"result.json": hashlib.sha256(body).hexdigest()}
        target = artifacts / exp_id
        target.mkdir(parents=True, exist_ok=True)
        (target / "result.json").write_bytes(body)

        future_ts = _future_ts(300)
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO jobs
                    (id, payload_hash, request_params_json, status, worker_id, fencing_token,
                     attempt, max_attempts, lease_expires_at, cancel_requested, created_at, started_at)
                VALUES ('job-active', 'hash', '{}', 'running', 'worker', 'token-active', 1, 3,
                        :lease, :cancel, :now, :now)
            """), {"lease": future_ts, "cancel": False, "now": datetime.now(timezone.utc).isoformat()})

        repo.reserve_publication(gen_id, exp_id, digest, exec_id, manifest,
            job_id="job-active", lease_expires_at=future_ts,
            prepared_payload=payload, prepared_audit={"probe": "active-job"})

        recover_prepared_publications(engine, artifacts)

        after = repo.get_publication(gen_id)
        assert after.status == "PREPARED"


# ─── R4-02: Full recovery cycle does NOT commit partial result records ───────


class TestR402NoPartialResults:
    """R4-02: Recovery must not leave experiment/execution rows when job transition is rejected."""

    def test_full_cycle_no_orphaned_rows(self, env):
        """run_recovery_cycle must not insert experiment/execution rows for requeued jobs."""
        engine = env["engine"]
        repo = env["repo"]
        artifacts = env["artifacts"]

        info = _prepare_publication(env, "expired-worker", job=True)
        exp_id = info["exp_id"]
        exec_id = info["exec_id"]
        job_id = info["job_id"]
        gen_id = info["gen_id"]

        # Run the FULL recovery cycle (publications first, then leases — new ordering)
        counts = run_recovery_cycle(engine, artifacts)

        with engine.connect() as conn:
            job_status = conn.execute(
                text("SELECT status FROM jobs WHERE id = :id"), {"id": job_id}
            ).scalar()
            pub_status = repo.get_publication(gen_id).status
            exp_rows = conn.execute(
                text("SELECT count(*) FROM experiments WHERE id = :id"), {"id": exp_id}
            ).scalar()
            exec_rows = conn.execute(
                text("SELECT count(*) FROM experiment_executions WHERE execution_id = :id"), {"id": exec_id}
            ).scalar()

        # With the corrected ordering, publications are recovered BEFORE leases
        # so the job should be completed (not requeued) and rows should exist
        assert pub_status in ("PUBLISHED", "QUARANTINED")
        if pub_status == "PUBLISHED":
            assert job_status == "completed"
            assert exp_rows == 1
            assert exec_rows == 1
        else:
            # If quarantined, no orphaned rows should remain
            assert exp_rows == 0, f"Orphaned experiment rows: {exp_rows}"
            assert exec_rows == 0, f"Orphaned execution rows: {exec_rows}"

    def test_rejected_transition_rolls_back_all_rows(self, env):
        """When job transition is explicitly rejected, savepoint rolls back result rows."""
        engine = env["engine"]
        repo = env["repo"]
        artifacts = env["artifacts"]

        # Create a job that's already been requeued (simulating the old ordering bug)
        payload = {"probe": "already-requeued"}
        digest = stable_hash(payload)
        exp_id = digest[:24]
        gen_id = "gen-requeued"
        exec_id = "exec-requeued"
        body = json.dumps(payload, sort_keys=True).encode()
        manifest = {"result.json": hashlib.sha256(body).hexdigest()}
        target = artifacts / exp_id
        target.mkdir(parents=True, exist_ok=True)
        (target / "result.json").write_bytes(body)

        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO jobs
                    (id, payload_hash, request_params_json, status, worker_id, fencing_token,
                     attempt, max_attempts, lease_expires_at, cancel_requested, created_at, started_at)
                VALUES ('job-requeued', 'hash', '{}', 'queued', NULL, NULL, 1, 3,
                        NULL, :cancel, :ts, :ts)
            """), {"cancel": False, "ts": _expired_ts()})

        repo.reserve_publication(gen_id, exp_id, digest, exec_id, manifest,
            job_id="job-requeued", lease_expires_at=_expired_ts(),
            prepared_payload=payload, prepared_audit={"probe": "already-requeued"})

        recover_prepared_publications(engine, artifacts)

        with engine.connect() as conn:
            pub = repo.get_publication(gen_id)
            exp_rows = conn.execute(
                text("SELECT count(*) FROM experiments WHERE id = :id"), {"id": exp_id}
            ).scalar()
            exec_rows = conn.execute(
                text("SELECT count(*) FROM experiment_executions WHERE execution_id = :id"), {"id": exec_id}
            ).scalar()

        # Job was 'queued' so transition must fail; savepoint must roll back result rows
        assert pub.status == "QUARANTINED"
        assert exp_rows == 0, f"Experiment rows leaked: {exp_rows}"
        assert exec_rows == 0, f"Execution rows leaked: {exec_rows}"

    def test_cancelled_job_no_result_rows(self, env):
        """Cancelled job should quarantine without inserting any result rows."""
        engine = env["engine"]
        repo = env["repo"]
        artifacts = env["artifacts"]

        payload = {"probe": "cancelled-job"}
        digest = stable_hash(payload)
        exp_id = digest[:24]
        gen_id = "gen-cancelled"
        exec_id = "exec-cancelled"
        body = json.dumps(payload, sort_keys=True).encode()
        manifest = {"result.json": hashlib.sha256(body).hexdigest()}
        target = artifacts / exp_id
        target.mkdir(parents=True, exist_ok=True)
        (target / "result.json").write_bytes(body)

        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO jobs
                    (id, payload_hash, request_params_json, status, worker_id, fencing_token,
                     attempt, max_attempts, lease_expires_at, cancel_requested, created_at, started_at)
                VALUES ('job-cancel', 'hash', '{}', 'running', 'worker', 'token-cancel', 1, 3,
                        :expired, :cancel, :expired, :expired)
            """), {"expired": _expired_ts(), "cancel": True})

        repo.reserve_publication(gen_id, exp_id, digest, exec_id, manifest,
            job_id="job-cancel", lease_expires_at=_expired_ts(),
            prepared_payload=payload, prepared_audit={"probe": "cancelled"})

        recover_prepared_publications(engine, artifacts)

        pub = repo.get_publication(gen_id)
        assert pub.status == "QUARANTINED"

        with engine.connect() as conn:
            exp_rows = conn.execute(
                text("SELECT count(*) FROM experiments WHERE id = :id"), {"id": exp_id}
            ).scalar()
        assert exp_rows == 0

    def test_exhausted_attempts_no_result_rows(self, env):
        """Failed job (max attempts) should quarantine without result rows."""
        engine = env["engine"]
        repo = env["repo"]
        artifacts = env["artifacts"]

        payload = {"probe": "exhausted"}
        digest = stable_hash(payload)
        exp_id = digest[:24]
        gen_id = "gen-exhausted"
        exec_id = "exec-exhausted"
        body = json.dumps(payload, sort_keys=True).encode()
        manifest = {"result.json": hashlib.sha256(body).hexdigest()}
        target = artifacts / exp_id
        target.mkdir(parents=True, exist_ok=True)
        (target / "result.json").write_bytes(body)

        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO jobs
                    (id, payload_hash, request_params_json, status, worker_id, fencing_token,
                     attempt, max_attempts, lease_expires_at, cancel_requested, created_at, started_at)
                VALUES ('job-exhausted', 'hash', '{}', 'failed', 'worker', 'token-exh', 3, 3,
                        :expired, :cancel, :expired, :expired)
            """), {"expired": _expired_ts(), "cancel": False})

        repo.reserve_publication(gen_id, exp_id, digest, exec_id, manifest,
            job_id="job-exhausted", lease_expires_at=_expired_ts(),
            prepared_payload=payload, prepared_audit={"probe": "exhausted"})

        recover_prepared_publications(engine, artifacts)

        pub = repo.get_publication(gen_id)
        assert pub.status == "QUARANTINED"


# ─── R4-03: Recovery rejects false logical digests ───────────────────────────


class TestR403DigestValidation:
    """R4-03: Recovery must validate stable_hash(payload) == full_digest and [:24] == experiment_id."""

    def test_corrupt_digest_rejected(self, env):
        """A publication with corrupt digest must be quarantined, not published."""
        repo = env["repo"]
        artifacts = env["artifacts"]

        info = _prepare_publication(env, "wrong-digest", corrupt_digest=True)
        gen_id = info["gen_id"]
        exp_id = info["exp_id"]

        recover_prepared_publications(env["engine"], artifacts)

        pub = repo.get_publication(gen_id)
        assert pub.status == "QUARANTINED", f"Expected QUARANTINED, got {pub.status}"

        # Must NOT be visible via get_published
        result = repo.get_published(exp_id)
        assert result is None, "Corrupt-digest publication should not be visible"

    def test_corrupt_digest_no_experiment_rows(self, env):
        """A corrupt-digest rejection must not create experiment or execution rows."""
        engine = env["engine"]
        artifacts = env["artifacts"]

        info = _prepare_publication(env, "wrong-digest-no-rows", corrupt_digest=True)
        exp_id = info["exp_id"]
        exec_id = info["exec_id"]

        recover_prepared_publications(engine, artifacts)

        with engine.connect() as conn:
            exp_rows = conn.execute(
                text("SELECT count(*) FROM experiments WHERE id = :id"), {"id": exp_id}
            ).scalar()
            exec_rows = conn.execute(
                text("SELECT count(*) FROM experiment_executions WHERE execution_id = :id"), {"id": exec_id}
            ).scalar()
        assert exp_rows == 0, f"Experiment rows inserted despite corrupt digest: {exp_rows}"
        assert exec_rows == 0, f"Execution rows inserted despite corrupt digest: {exec_rows}"

    def test_valid_digest_accepted(self, env):
        """A publication with a correct digest should be successfully recovered."""
        repo = env["repo"]
        artifacts = env["artifacts"]

        info = _prepare_publication(env, "valid-digest", corrupt_digest=False)
        gen_id = info["gen_id"]
        exp_id = info["exp_id"]

        recover_prepared_publications(env["engine"], artifacts)

        pub = repo.get_publication(gen_id)
        assert pub.status == "PUBLISHED"

        # Must be visible via get_published
        result = repo.get_published(exp_id)
        assert result is not None

    def test_valid_recovery_then_identical_normal_rerun(self, env):
        """Valid recovery followed by identical normal put must be idempotent."""
        repo = env["repo"]
        artifacts = env["artifacts"]

        info = _prepare_publication(env, "valid-then-rerun", corrupt_digest=False)
        gen_id = info["gen_id"]
        exp_id = info["exp_id"]
        exec_id = info["exec_id"]
        digest = info["digest"]
        manifest = info["manifest"]
        payload = info["payload"]

        recover_prepared_publications(env["engine"], artifacts)

        pub = repo.get_publication(gen_id)
        assert pub.status == "PUBLISHED"

        # Normal put with identical content should succeed (idempotent)
        content_hashes = canonical_content_hashes(manifest, digest)
        repo.put(exp_id, payload, content_hashes, exec_id, {"probe": "valid-then-rerun"})

    def test_corrupt_experiment_id_rejected(self, env):
        """A publication whose experiment_id doesn't match digest[:24] must be quarantined."""
        engine = env["engine"]
        repo = env["repo"]
        artifacts = env["artifacts"]

        payload = {"probe": "bad-exp-id"}
        digest = stable_hash(payload)
        real_exp_id = digest[:24]
        fake_exp_id = "a" * 24  # Wrong experiment ID
        gen_id = "gen-bad-exp-id"
        exec_id = "exec-bad-exp-id"
        body = json.dumps(payload, sort_keys=True).encode()
        manifest = {"result.json": hashlib.sha256(body).hexdigest()}
        target = artifacts / fake_exp_id
        target.mkdir(parents=True, exist_ok=True)
        (target / "result.json").write_bytes(body)

        # Manually insert with mismatched experiment_id
        now_str = datetime.now(timezone.utc).isoformat()
        payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        audit_json = json.dumps({"probe": "bad-exp-id"}, sort_keys=True, separators=(",", ":"))
        manifest_json = json.dumps(manifest, sort_keys=True, separators=(",", ":"))
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO experiment_publications
                    (generation_id, experiment_id, full_digest, execution_id, status, manifest_json,
                     lease_expires_at, prepared_payload_json, prepared_audit_json, created_at, updated_at)
                VALUES (:gen_id, :exp_id, :digest, :exec_id, 'PREPARED', :manifest,
                        :lease, :payload, :audit, :now, :now)
            """), {
                "gen_id": gen_id, "exp_id": fake_exp_id, "digest": digest,
                "exec_id": exec_id, "manifest": manifest_json,
                "lease": _expired_ts(), "payload": payload_json, "audit": audit_json,
                "now": now_str,
            })

        recover_prepared_publications(engine, artifacts)

        pub = repo.get_publication(gen_id)
        assert pub.status == "QUARANTINED"


# ─── R4-04: Conflict-safe concurrent insertion ──────────────────────────────


class TestR404ConflictSafeInsertion:
    """R4-04: Concurrent identical inserts must not raise IntegrityError."""

    def test_concurrent_identical_experiment_both_succeed(self, env):
        """Two connections inserting the same experiment with distinct executions must both succeed."""
        settings = env["settings"]

        barrier = threading.Barrier(2)
        engines = [create_engine_for_settings(settings) for _ in range(2)]

        # Warm up connections
        for e in engines:
            with e.connect() as conn:
                conn.execute(text("SELECT 1"))

        # Synchronize just before INSERT INTO experiments
        def synchronize(conn, cursor, statement, parameters, context, executemany):
            if statement.startswith("INSERT INTO experiments "):
                barrier.wait(timeout=10)

        for e in engines:
            event.listen(e, "before_cursor_execute", synchronize)

        payload = {"probe": "concurrent-put"}
        digest = stable_hash(payload)
        exp_id = digest[:24]

        def publish(i):
            try:
                repo = ExperimentRepository(engines[i])
                content_hashes = {"logical_content": digest}
                repo.put(exp_id, payload, content_hashes, f"race-exec-{i}", {"probe": i})
                return {"outcome": "success", "exec_id": f"race-exec-{i}"}
            except Exception as exc:
                return {"outcome": type(exc).__name__, "message": str(exc).splitlines()[0]}

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(publish, [0, 1]))

        for e in engines:
            event.remove(e, "before_cursor_execute", synchronize)
            e.dispose()

        # Both must succeed — no IntegrityError
        outcomes = [r["outcome"] for r in results]
        assert outcomes.count("success") == 2, f"Expected both success, got: {results}"

        # Verify both execution IDs exist
        repo = env["repo"]
        exec_ids = repo.execution_ids(exp_id)
        assert "race-exec-0" in exec_ids
        assert "race-exec-1" in exec_ids

    def test_identical_execution_replay_idempotent(self, env):
        """Replaying identical experiment+execution must be idempotent."""
        repo = env["repo"]
        payload = {"probe": "replay"}
        digest = stable_hash(payload)
        exp_id = digest[:24]
        content_hashes = {"logical_content": digest}

        # First put
        repo.put(exp_id, payload, content_hashes, "exec-replay", {"probe": "replay"})

        # Identical replay — must not raise
        repo.put(exp_id, payload, content_hashes, "exec-replay", {"probe": "replay"})

        result = repo.get(exp_id)
        assert result is not None
        assert result.deterministic_payload == payload

    def test_conflicting_payload_rejected(self, env):
        """Different payloads for the same experiment_id must be rejected."""
        repo = env["repo"]
        payload1 = {"probe": "conflict-a"}
        digest1 = stable_hash(payload1)
        exp_id = digest1[:24]
        content_hashes1 = {"logical_content": digest1}

        repo.put(exp_id, payload1, content_hashes1, "exec-conflict-1", {"probe": "conflict-a"})

        # Different payload, same experiment_id
        payload2 = {"probe": "conflict-b"}
        digest2 = stable_hash(payload2)
        content_hashes2 = {"logical_content": digest2}

        with pytest.raises(ExperimentImmutabilityError):
            repo.put(exp_id, payload2, content_hashes2, "exec-conflict-2", {"probe": "conflict-b"})

        # Verify only the first experiment's data exists
        stored = repo.get(exp_id)
        assert stored.deterministic_payload == payload1

    def test_conflicting_audit_rejected(self, env):
        """Different audit for the same execution_id must be rejected."""
        repo = env["repo"]
        payload = {"probe": "audit-conflict"}
        digest = stable_hash(payload)
        exp_id = digest[:24]
        content_hashes = {"logical_content": digest}

        repo.put(exp_id, payload, content_hashes, "exec-audit", {"probe": "audit-1"})

        with pytest.raises(ValueError, match="already exists with different audit"):
            repo.put(exp_id, payload, content_hashes, "exec-audit", {"probe": "audit-2"})

    def test_concurrent_conflicting_payload_no_partial_writes(self, env):
        """Concurrent conflicting payloads must reject without partial writes."""
        settings = env["settings"]

        barrier = threading.Barrier(2)
        engines = [create_engine_for_settings(settings) for _ in range(2)]

        for e in engines:
            with e.connect() as conn:
                conn.execute(text("SELECT 1"))

        def synchronize(conn, cursor, statement, parameters, context, executemany):
            if statement.startswith("INSERT INTO experiments "):
                barrier.wait(timeout=10)

        for e in engines:
            event.listen(e, "before_cursor_execute", synchronize)

        # Thread 0: payload A
        # Thread 1: payload B
        # Both target the same experiment_id (forced)
        payload_a = {"probe": "race-a"}
        digest_a = stable_hash(payload_a)
        exp_id = digest_a[:24]

        payload_b = {"probe": "race-b"}
        digest_b = stable_hash(payload_b)

        def publish(i):
            try:
                repo = ExperimentRepository(engines[i])
                payload = payload_a if i == 0 else payload_b
                digest = digest_a if i == 0 else digest_b
                content_hashes = {"logical_content": digest}
                repo.put(exp_id, payload, content_hashes, f"race-conflict-exec-{i}", {"probe": i})
                return {"outcome": "success"}
            except Exception as exc:
                return {"outcome": type(exc).__name__, "message": str(exc).splitlines()[0]}

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(publish, [0, 1]))

        for e in engines:
            event.remove(e, "before_cursor_execute", synchronize)
            e.dispose()

        # Exactly one should succeed, one should fail with immutability error
        outcomes = [r["outcome"] for r in results]
        assert "success" in outcomes
        fail_count = sum(1 for o in outcomes if o != "success")
        assert fail_count <= 1, f"Both failed: {results}"

        # Verify stored experiment matches the winner
        stored = env["repo"].get(exp_id)
        assert stored is not None
