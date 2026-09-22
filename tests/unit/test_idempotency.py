"""Unit tests for Gate 4 job queue idempotency guarantees."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine

from shiftguard.jobs.queue import IdempotencyConflictError, JobQueue
from shiftguard.migrations import upgrade_database
from shiftguard.settings import Settings


@pytest.fixture
def test_queue(tmp_path):
    db_file = tmp_path / "idempotency_test.db"
    settings = Settings(SHIFTGUARD_DB_URL=f"sqlite:///{db_file}")
    upgrade_database(settings)
    engine = create_engine(f"sqlite:///{db_file}")
    try:
        yield JobQueue(engine)
    finally:
        engine.dispose()


def test_enqueue_without_idempotency_key_creates_distinct_jobs(test_queue):
    params = {"preset_name": "bank-outage-50"}
    job1 = test_queue.enqueue(params)
    job2 = test_queue.enqueue(params)

    assert job1.id != job2.id
    assert job1.status.value == "queued"
    assert job2.status.value == "queued"


def test_idempotent_replay_with_same_key_and_payload(test_queue):
    key = "user-action-12345"
    params = {"preset_name": "bank-outage-50", "master_seed": 31001}

    job1 = test_queue.enqueue(params, idempotency_key=key)
    job2 = test_queue.enqueue(params, idempotency_key=key)

    assert job1.id == job2.id
    assert job1.payload_hash == job2.payload_hash
    assert job2.idempotency_key == key


def test_idempotency_conflict_with_different_payload(test_queue):
    key = "user-action-12345"
    params1 = {"preset_name": "bank-outage-50", "master_seed": 31001}
    params2 = {"preset_name": "bank-stress", "master_seed": 42}

    job1 = test_queue.enqueue(params1, idempotency_key=key)
    assert job1.idempotency_key == key

    with pytest.raises(IdempotencyConflictError, match="already associated with a different payload"):
        test_queue.enqueue(params2, idempotency_key=key)
