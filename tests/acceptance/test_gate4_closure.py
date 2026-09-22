"""Fixed acceptance counterexamples. Failing tests are open defects, never xfails."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import json
from threading import Event
from types import SimpleNamespace
from uuid import uuid4

from alembic import command
import pytest
from sqlalchemy import event, text

from shiftguard.datasets.bank import BankDataset, FROZEN_BANK_SOURCE, write_clean_csv
from shiftguard.experiments.ids import stable_hash
from shiftguard.jobs.continuation import ContinuationService
from shiftguard.jobs.queue import JobQueue
from shiftguard.migrations import get_alembic_config, upgrade_database
from shiftguard.settings import Settings
from shiftguard.storage.db import create_engine_for_settings
from shiftguard.storage.repositories import ExperimentRepository


@pytest.fixture(params=["sqlite", "postgres"])
def repository(request, tmp_path, monkeypatch):
    """A private SQLite file or a unique schema in the explicitly supplied test DB."""
    import os
    if request.param == "sqlite":
        settings = Settings(SHIFTGUARD_DB_URL=f"sqlite:///{tmp_path / 'closure.db'}",
                            SHIFTGUARD_ENVIRONMENT="local")
        upgrade_database(settings)
        engine = create_engine_for_settings(settings)
        try:
            yield ExperimentRepository(engine)
        finally:
            engine.dispose()
        return
    url = os.environ.get("SHIFTGUARD_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("BLOCKED: isolated PostgreSQL 16 test URL is missing")
    settings = Settings(SHIFTGUARD_DB_URL=url, SHIFTGUARD_ENVIRONMENT="hosted")
    admin = create_engine_for_settings(settings)
    schema = "sg_closure_" + uuid4().hex
    created = False
    engine = None
    try:
        with admin.begin() as conn:
            assert conn.execute(text("SHOW server_version_num")).scalar_one().startswith("16")
            conn.execute(text(f'CREATE SCHEMA "{schema}"'))
            created = True
        engine = create_engine_for_settings(settings)

        @event.listens_for(engine, "connect")
        def set_schema(dbapi, _record):
            previous = dbapi.autocommit
            dbapi.autocommit = True
            try:
                with dbapi.cursor() as cursor:
                    cursor.execute(f'SET search_path TO "{schema}"')
            finally:
                dbapi.autocommit = previous

        with engine.begin() as conn:
            cfg = get_alembic_config(settings)
            cfg.attributes["connection"] = conn
            command.upgrade(cfg, "head")
        yield ExperimentRepository(engine)
    finally:
        if engine is not None:
            engine.dispose()
        if created:
            # Only the freshly generated schema belonging to this fixture.
            with admin.begin() as conn:
                conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


def synthetic_bank(tmp_path):
    row = {"row_id": 1, "age": "30", "job": "fabricated", "marital": "single",
           "education": "secondary", "default": "no", "housing": "yes", "loan": "no",
           "pdays": "999", "previous": "0", "poutcome": "nonexistent", "y": 0}
    path = tmp_path / "fabricated.csv"
    digest = write_clean_csv([row], path)
    return path, {**FROZEN_BANK_SOURCE, "clean_sha256": digest, "rows": 1}


@pytest.mark.parametrize("flag", ["synthetic", "allow_synthetic"])
@pytest.mark.parametrize("value", [True, "false"])
def test_manifest_cannot_disable_production_identity(tmp_path, flag, value):
    path, manifest = synthetic_bank(tmp_path)
    with pytest.raises(ValueError, match="frozen|canonical|synthetic"):
        BankDataset.from_clean_csv(path, {**manifest, flag: value})


def test_explicit_synthetic_fixture_remains_usable(tmp_path):
    path, manifest = synthetic_bank(tmp_path)
    assert len(BankDataset.from_synthetic_csv(path, manifest).rows) == 1


def test_resume_cannot_complete_stale_dependencies(repository, monkeypatch):
    queue = JobQueue(repository.engine)
    service = ContinuationService(repository.engine)
    session = service.create_session()
    first = queue.enqueue({}, session_id=session.id)
    second = queue.enqueue({"second": True}, session_id=session.id)
    with repository.engine.begin() as conn:
        conn.execute(text("UPDATE jobs SET status='completed',result_json='{}' WHERE id=:id"), {"id": first.id})
    service.bind_jobs_to_session(session.id, [first.id])
    original = queue.get_job
    started = Event()
    finished = Event()
    binding = None

    def bind():
        started.set()
        try:
            # Independent connection: permits either version checking or serialization.
            service.bind_jobs_to_session(session.id, [second.id])
        except ValueError as exc:
            return str(exc)
        finally:
            finished.set()
        return None

    def get_and_bind(job_id):
        nonlocal binding
        row = original(job_id)
        if job_id == first.id and binding is None:
            binding = executor.submit(bind)
            assert started.wait(5), "Concurrent binder never started"
            # A write lock may legitimately defer binding until resume commits.
            finished.wait(1)
        return row

    monkeypatch.setattr(queue, "get_job", get_and_bind)
    with ThreadPoolExecutor(max_workers=1) as executor:
        status, _ = service.resume(session.id, session.active_nonce, queue)
        assert binding is not None, "Resume never inspected its dependency"
        bind_error = binding.result(timeout=10)
    updated = service.get_session(session.id)
    if bind_error is not None:
        # Serializing resume before bind is also valid: the late bind is rejected.
        assert "terminal" in bind_error.lower() or "transitioned" in bind_error.lower()
        assert status == 200 and updated.status.value == "COMPLETED"
        assert set(updated.required_job_ids) == {first.id}
        return
    assert status in (202, 409), "Resume consumed a stale dependency snapshot"
    assert updated.status.value == "WAITING_FOR_JOB"
    assert set(updated.required_job_ids) == {first.id, second.id}
    assert updated.active_nonce == session.active_nonce
    with repository.engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM continuation_receipts WHERE session_id=:id"), {"id": session.id}).scalar_one() == 0


@pytest.mark.parametrize("wrong_owner", [False, True])
def test_publication_binds_preparing_attempt(repository, wrong_owner):
    queue = JobQueue(repository.engine)
    queue.enqueue({})
    job = queue.claim_next_job("worker")
    payload = {"closure": "owner"}
    digest = stable_hash(payload)
    exp = digest[:24]
    repository.reserve_publication("generation", exp, digest, "execution", {"result.json": "h"},
        job_id=job.id, prepared_payload=payload, prepared_audit={"run": 1},
        attempt=job.attempt + 1 if wrong_owner else job.attempt,
        fencing_token="wrong-token" if wrong_owner else job.fencing_token)
    def finalize():
        repository.put(exp, payload, {"logical_content": digest}, "execution", {"run": 1},
            generation_id="generation", job_context=(job.id, job.fencing_token))
    if wrong_owner:
        from shiftguard.jobs.models import PublicationLostOwnershipError, WorkerFencedOutException
        with pytest.raises((PublicationLostOwnershipError, WorkerFencedOutException)):
            finalize()
    else:
        finalize()
    with repository.engine.connect() as conn:
        count = conn.execute(text("SELECT count(*) FROM experiments WHERE id=:id"), {"id": exp}).scalar_one()
        audits = conn.execute(text("SELECT count(*) FROM experiment_executions WHERE execution_id='execution'")).scalar_one()
    assert count == audits == (0 if wrong_owner else 1)
    assert queue.get_job(job.id).status.value == ("running" if wrong_owner else "completed")
    assert repository.get_publication("generation").status == ("PREPARED" if wrong_owner else "PUBLISHED")


def test_gate2_rejects_invented_logical_identity(tmp_path, monkeypatch):
    """Exercise the real verifier orchestrator; stub only subprocess/database I/O."""
    import verification.verify_gate2_reproduction as verifier
    from tests.unit.test_verifier_hygiene import (
        _create_dummy_artifacts, _create_dummy_run_payload, _seed_sqlite_experiment,
    )
    exp = "invented-not-a-content-id"
    fake_app = tmp_path / "app"
    hashes = _create_dummy_artifacts(fake_app / "var/artifacts" / exp)
    output = tmp_path / "output"
    monkeypatch.setattr(verifier, "APP", fake_app)
    monkeypatch.setenv("SHIFTGUARD_VERIFICATION_OUTPUT", str(output))
    monkeypatch.setenv("SHIFTGUARD_TEST_POSTGRES_URL", "postgresql://unused/closure")
    monkeypatch.setenv("SHIFTGUARD_EXPECTED_COMMIT", "test_commit")
    audit = {"provenance": {"git": {"available": True, "dirty": False, "head": "test_commit"}}}
    calls = 0

    def run(cmd, **kwargs):
        nonlocal calls
        calls += 1
        data = _create_dummy_run_payload(exp, f"exec-{calls}", content_hashes=hashes)
        url = cmd[cmd.index("--db-url") + 1]
        if url.startswith("sqlite:///"):
            _seed_sqlite_experiment(url[len("sqlite:///"):], exp, f"exec-{calls}", data, audit)
        return SimpleNamespace(returncode=0, stdout=json.dumps(data), stderr="")

    class Postgres:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def execute(self, *args):
            return SimpleNamespace(
                fetchone=lambda: (json.dumps(_create_dummy_run_payload(exp, "exec-1", content_hashes=hashes)),),
                fetchall=lambda: [("exec-3", json.dumps(audit))])

    monkeypatch.setattr(verifier.subprocess, "run", run)
    monkeypatch.setattr(verifier.psycopg, "connect", lambda _: Postgres())
    with pytest.raises((AssertionError, ValueError), match="(?i)identity|digest|experiment|hash|condition|projection"):
        verifier.main()
    assert not (output / "verification.json").exists()


@pytest.mark.parametrize("missing", ["job_id", "attempt", "fencing_token", "all"])
def test_publication_rejects_partial_worker_authority(repository, missing):
    """I05 already requires conservative rejection of partial/legacy ownership."""
    from shiftguard.jobs.models import PublicationLostOwnershipError, WorkerFencedOutException

    queue = JobQueue(repository.engine)
    queue.enqueue({})
    job = queue.claim_next_job("worker")
    payload = {"closure": "partial-authority"}
    digest = stable_hash(payload)
    experiment = digest[:24]
    owner = {"job_id": job.id, "attempt": job.attempt, "fencing_token": job.fencing_token}
    if missing == "all":
        owner = {key: None for key in owner}
    else:
        owner[missing] = None
    with repository.engine.connect() as conn:
        events_before = conn.execute(text("SELECT count(*) FROM job_events WHERE job_id=:id"), {"id": job.id}).scalar_one()
    with pytest.raises((PublicationLostOwnershipError, WorkerFencedOutException)):
        # Either reservation or finalization may reject incomplete worker authority.
        repository.reserve_publication("partial-generation", experiment, digest, "partial-execution",
            {"result.json": "h"}, prepared_payload=payload, prepared_audit={"run": 1}, **owner)
        repository.put(experiment, payload, {"logical_content": digest}, "partial-execution", {"run": 1},
            generation_id="partial-generation", job_context=(job.id, job.fencing_token))
    with repository.engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM experiments WHERE id=:id"), {"id": experiment}).scalar_one() == 0
        assert conn.execute(text("SELECT count(*) FROM experiment_executions WHERE execution_id='partial-execution'")).scalar_one() == 0
        assert conn.execute(text("SELECT count(*) FROM job_events WHERE job_id=:id"), {"id": job.id}).scalar_one() == events_before
    assert queue.get_job(job.id).status.value == "running"
    publication = repository.get_publication("partial-generation")
    assert publication is None or publication.status != "PUBLISHED"


def test_gate2_failed_attempt_preserves_previous_evidence(tmp_path, monkeypatch):
    """I08 forbids deleting a legacy result while introducing attempt isolation."""
    import verification.verify_gate2_reproduction as verifier

    output = tmp_path / "old-evidence"
    output.mkdir()
    previous = b'{"status":"passed","experiment_id":"historical-evidence-sentinel"}\n'
    historical = output / "verification.json"
    historical.write_bytes(previous)
    monkeypatch.setenv("SHIFTGUARD_VERIFICATION_OUTPUT", str(output))
    monkeypatch.delenv("SHIFTGUARD_TEST_POSTGRES_URL", raising=False)
    monkeypatch.setattr(verifier, "get_expected_commit", lambda: "candidate-without-backend")
    with pytest.raises(RuntimeError, match="SHIFTGUARD_TEST_POSTGRES_URL"):
        verifier.main()
    pointer = json.loads((output / "current_attempt.json").read_text(encoding="utf-8"))
    assert pointer["status"] == "FAILED"
    preserved = [path for path in output.rglob("*.json") if path.read_bytes() == previous]
    assert preserved, "Previous evidence was deleted instead of retained or archived"


@pytest.mark.parametrize("fault", ["missing_digest", "forged_digest", "wrong_experiment_id"])
def test_publication_rejects_invalid_prepared_content_identity(repository, fault):
    """I05 binds staged content to its digest/ID on normal and recovery paths."""
    from shiftguard.jobs.models import PublicationLostOwnershipError

    queue = JobQueue(repository.engine)
    queue.enqueue({})
    job = queue.claim_next_job("worker")
    payload = {"closure": "content-identity"}
    digest = "0" * 64 if fault == "forged_digest" else stable_hash(payload)
    experiment = "1" * 24 if fault == "wrong_experiment_id" else digest[:24]
    hashes = {} if fault == "missing_digest" else {"logical_content": digest}
    with pytest.raises((PublicationLostOwnershipError, ValueError)):
        repository.reserve_publication("content-generation", experiment, digest, "content-execution",
            {"result.json": "h"}, job_id=job.id, attempt=job.attempt, fencing_token=job.fencing_token,
            prepared_payload=payload, prepared_audit={"run": 1})
        repository.put(experiment, payload, hashes, "content-execution", {"run": 1},
            generation_id="content-generation", job_context=(job.id, job.fencing_token))
    with repository.engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM experiments WHERE id=:id"), {"id": experiment}).scalar_one() == 0
        assert conn.execute(text("SELECT count(*) FROM experiment_executions WHERE execution_id='content-execution'")).scalar_one() == 0
    assert queue.get_job(job.id).status.value == "running"
    publication = repository.get_publication("content-generation")
    assert publication is None or publication.status != "PUBLISHED"
