"""Publication ownership across independent processes, beyond sequential checks."""
from multiprocessing import get_context

import pytest
from sqlalchemy import event, text

from shiftguard.jobs.models import PublicationContentionError
from shiftguard.jobs.queue import JobQueue
from shiftguard.migrations import upgrade_database
from shiftguard.settings import Settings
from shiftguard.storage.db import create_engine_for_settings
from shiftguard.storage.repositories import ExperimentRepository


def _reserve_in_process(db_url, generation, paused, release, entered, done, results):
    engine = create_engine_for_settings(Settings(SHIFTGUARD_DB_URL=db_url))

    def before_sql(conn, cursor, statement, parameters, context, executemany):
        entered.set()
        if paused is not None and statement.startswith(
            "UPDATE experiment_publications SET status = 'ABANDONED'"
        ):
            paused.set()
            if not release.wait(10):
                raise RuntimeError("Timed out waiting for reservation test release")

    event.listen(engine, "before_cursor_execute", before_sql)
    try:
        ExperimentRepository(engine).reserve_publication(
            generation, "same-experiment", "d" * 64, generation + "-execution",
            {"result.json": "h"},
        )
        results.put((generation, "reserved"))
    except PublicationContentionError:
        results.put((generation, "contended"))
    except Exception as exc:
        results.put((generation, type(exc).__name__))
    finally:
        engine.dispose()
        done.set()


def test_simultaneous_first_reservation_preserves_live_owner_across_processes(tmp_path):
    db_url = f"sqlite:///{tmp_path / 'processes.db'}"
    upgrade_database(Settings(SHIFTGUARD_DB_URL=db_url))
    ctx = get_context("spawn")
    paused, release, entered1, entered2, done1, done2 = [ctx.Event() for _ in range(6)]
    results = ctx.Queue()
    first = ctx.Process(target=_reserve_in_process,
        args=(db_url, "first", paused, release, entered1, done1, results))
    second = ctx.Process(target=_reserve_in_process,
        args=(db_url, "second", None, release, entered2, done2, results))
    try:
        first.start()
        assert paused.wait(10), "First process never reached reservation transition"
        second.start()
        assert entered2.wait(10), "Second process never attempted database access"
        # On the broken implementation the second process can commit here and
        # the first subsequently abandons it. Correct serialization blocks it.
        done2.wait(0.5)
    finally:
        release.set()
        for process in (first, second):
            if process.pid is not None:
                process.join(15)
                if process.is_alive():
                    process.terminate()
                    process.join(5)
    assert first.exitcode == second.exitcode == 0
    assert sorted([results.get(timeout=5), results.get(timeout=5)]) == [
        ("first", "reserved"), ("second", "contended")
    ]
    results.close()
    results.join_thread()
    engine = create_engine_for_settings(Settings(SHIFTGUARD_DB_URL=db_url))
    try:
        with engine.connect() as conn:
            assert conn.execute(text(
                "SELECT generation_id,status FROM experiment_publications"
            )).all() == [("first", "PREPARED")]
    finally:
        engine.dispose()


def test_worker_heartbeat_lease_protects_expired_publication_deadline(tmp_path):
    settings = Settings(SHIFTGUARD_DB_URL=f"sqlite:///{tmp_path / 'worker.db'}")
    upgrade_database(settings)
    engine = create_engine_for_settings(settings)
    try:
        queue = JobQueue(engine)
        queue.enqueue({"preset_name": "bank-baseline"})
        job = queue.claim_next_job("owner", lease_seconds=90)
        repo = ExperimentRepository(engine)
        repo.reserve_publication("live", "same", "d" * 64, "exec-live", {"r": "h"},
            job_id=job.id, lease_expires_at="2000-01-01T00:00:00+00:00")
        with pytest.raises(PublicationContentionError):
            repo.reserve_publication("other", "same", "d" * 64, "exec-other", {"r": "h"})
        assert repo.get_publication("live").status == "PREPARED"
        assert repo.get_publication("other") is None
    finally:
        engine.dispose()
