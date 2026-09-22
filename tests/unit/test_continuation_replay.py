"""Unit tests for Gate 4 durable continuation replay receipts and concurrent resumption."""

from __future__ import annotations

import threading
import pytest
from sqlalchemy import create_engine

from shiftguard.jobs.continuation import ContinuationService
from shiftguard.jobs.queue import JobQueue
from shiftguard.migrations import upgrade_database
from shiftguard.settings import Settings


@pytest.fixture
def continuation_db(tmp_path):
    db_file = tmp_path / "continuation.db"
    settings = Settings(SHIFTGUARD_DB_URL=f"sqlite:///{db_file}")
    upgrade_database(settings)
    engine = create_engine(f"sqlite:///{db_file}")
    try:
        yield engine, db_file
    finally:
        engine.dispose()


def test_durable_continuation_replay_returns_saved_receipt(continuation_db):
    """G4-06: Identical resumption retry returns 200 with saved receipt, NOT 403."""
    engine, _ = continuation_db
    service = ContinuationService(engine)
    queue = JobQueue(engine)

    # 1. Create agent session and bind completed job
    session = service.create_session(initial_state={"stage": "init"})
    session_id = session.id
    initial_nonce = session.active_nonce

    job = queue.enqueue({"preset_name": "bank-outage-50"})
    claimed = queue.claim_next_job("worker-1", 60)
    queue.mark_completed(job.id, claimed.fencing_token, "exp-1", {"status": "ok"})
    service.bind_jobs_to_session(session_id, [job.id])

    # 2. First resume call transitions session to COMPLETED and records receipt
    code1, res1 = service.resume(session_id, initial_nonce, queue=queue)
    assert code1 == 200
    assert res1["session_id"] == session_id
    assert res1["status"] == "COMPLETED"
    new_nonce = res1["nonce"]
    assert new_nonce != initial_nonce

    # 3. Simulate lost response: Client retries with ORIGINAL nonce
    # Prior defect returned 403 because nonce had rotated.
    # Fixed behavior must return 200 with identical response payload from durable receipt!
    code2, res2 = service.resume(session_id, initial_nonce, queue=queue)
    assert code2 == 200
    assert res2 == res1


def test_concurrent_resumption_has_single_winner_and_safe_replay(continuation_db):
    """G4-06: Concurrent resumption with identical nonce guarantees atomic single-winner."""
    engine, _ = continuation_db
    service = ContinuationService(engine)
    queue = JobQueue(engine)

    session = service.create_session(initial_state={"count": 0})
    session_id = session.id
    nonce = session.active_nonce

    job = queue.enqueue({"preset_name": "bank-outage-50"})
    claimed = queue.claim_next_job("worker-1", 60)
    queue.mark_completed(job.id, claimed.fencing_token, "exp-1", {"status": "ok"})
    service.bind_jobs_to_session(session_id, [job.id])

    barrier = threading.Barrier(2)
    results = [None, None]

    def _caller(idx):
        barrier.wait()
        local_service = ContinuationService(engine)
        local_queue = JobQueue(engine)
        results[idx] = local_service.resume(session_id, nonce, queue=local_queue)

    t1 = threading.Thread(target=_caller, args=(0,))
    t2 = threading.Thread(target=_caller, args=(1,))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    code1, res1 = results[0]
    code2, res2 = results[1]

    # Both callers must succeed with 200 and return identical rotated nonce
    assert code1 == 200
    assert code2 == 200
    assert res1["session_id"] == session_id
    assert res2["session_id"] == session_id
    assert res1["nonce"] == res2["nonce"]
    assert res1["status"] == "COMPLETED"


def test_receipt_replay_after_service_restart(continuation_db):
    """G4-06: Durable receipts persist across process/engine restarts."""
    engine, db_file = continuation_db
    service = ContinuationService(engine)
    queue = JobQueue(engine)

    session = service.create_session(initial_state={"step": 1})
    session_id = session.id
    nonce = session.active_nonce

    job = queue.enqueue({"preset_name": "bank-outage-50"})
    claimed = queue.claim_next_job("worker-1", 60)
    queue.mark_completed(job.id, claimed.fencing_token, "exp-1", {"status": "ok"})
    service.bind_jobs_to_session(session_id, [job.id])

    code1, res1 = service.resume(session_id, nonce, queue=queue)
    assert code1 == 200

    # Dispose engine and simulate brand-new process restart
    engine.dispose()
    new_engine = create_engine(f"sqlite:///{db_file}")
    try:
        new_service = ContinuationService(new_engine)
        new_queue = JobQueue(new_engine)
        code2, res2 = new_service.resume(session_id, nonce, queue=new_queue)
        assert code2 == 200
        assert res2 == res1
    finally:
        new_engine.dispose()
