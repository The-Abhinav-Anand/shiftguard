"""Tests for agent request durable persistence, idempotency, and atomic lease claims."""

from __future__ import annotations

import os
from uuid import uuid4
import pytest
from sqlalchemy import create_engine, text

from shiftguard.agent.store import AgentStore, IdempotencyConflictError
from shiftguard.migrations import upgrade_database
from shiftguard.settings import Settings


@pytest.fixture
def sqlite_store(tmp_path):
    db_file = tmp_path / "test_persistence.db"
    settings = Settings(SHIFTGUARD_DB_URL=f"sqlite:///{db_file}")
    upgrade_database(settings)
    engine = create_engine(f"sqlite:///{db_file}")
    return AgentStore(engine)


def test_create_and_retrieve_request(sqlite_store: AgentStore):
    req, is_new = sqlite_store.create_or_get_request(
        session_id="sess_001",
        intent_key="intent_unique_1",
        canonical_body_hash="hash_abc",
        prompt="Initial prompt",
    )
    assert is_new is True
    assert req.status == "RUNNING"
    assert req.turn_count == 0
    assert req.generation == 1

    # Fetch by ID
    loaded = sqlite_store.get_request(req.id)
    assert loaded is not None
    assert loaded.id == req.id
    assert loaded.prompt == "Initial prompt"


def test_idempotent_replay_with_matching_payload(sqlite_store: AgentStore):
    req1, is_new1 = sqlite_store.create_or_get_request(
        session_id="sess_001",
        intent_key="intent_replay",
        canonical_body_hash="hash_same",
        prompt="Replay prompt",
    )
    assert is_new1 is True

    # Replay with same session, intent, and body hash
    req2, is_new2 = sqlite_store.create_or_get_request(
        session_id="sess_001",
        intent_key="intent_replay",
        canonical_body_hash="hash_same",
        prompt="Replay prompt",
    )
    assert is_new2 is False
    assert req1.id == req2.id


def test_idempotency_conflict_on_changed_payload(sqlite_store: AgentStore):
    sqlite_store.create_or_get_request(
        session_id="sess_001",
        intent_key="intent_conflict",
        canonical_body_hash="hash_initial",
        prompt="Initial prompt",
    )

    # Replay with same intent_key but changed body hash -> must raise IdempotencyConflictError
    with pytest.raises(IdempotencyConflictError):
        sqlite_store.create_or_get_request(
            session_id="sess_001",
            intent_key="intent_conflict",
            canonical_body_hash="hash_different",
            prompt="Different prompt",
        )


def test_atomic_lease_claim_and_generation_increment(sqlite_store: AgentStore):
    req, _ = sqlite_store.create_or_get_request(
        session_id="sess_001",
        intent_key="intent_lease",
        canonical_body_hash="hash_lease",
        prompt="Lease test",
    )

    # Worker 1 claims lease
    claimed1, req1 = sqlite_store.claim_lease(req.id, worker_id="worker_1", lease_seconds=30)
    assert claimed1 is True
    assert req1 is not None
    assert req1.worker_id == "worker_1"
    assert req1.generation == req.generation + 1

    # Worker 2 tries to claim active unexpired lease -> rejected
    claimed2, _ = sqlite_store.claim_lease(req.id, worker_id="worker_2", lease_seconds=30)
    assert claimed2 is False

    # Worker 1 renews own lease -> allowed
    claimed1_renew, req1_renew = sqlite_store.claim_lease(req.id, worker_id="worker_1", lease_seconds=30)
    assert claimed1_renew is True
    assert req1_renew is not None
    assert req1_renew.generation == req1.generation + 1


def test_stale_generation_update_rejected(sqlite_store: AgentStore):
    req, _ = sqlite_store.create_or_get_request(
        session_id="sess_001",
        intent_key="intent_gen",
        canonical_body_hash="hash_gen",
        prompt="Generation test",
    )

    # Attempt update with wrong generation
    updated = sqlite_store.update_request(
        request_id=req.id,
        expected_generation=999,  # Mismatch
        status="COMPLETED",
    )
    assert updated is False

    # Update with expected generation succeeds
    updated_valid = sqlite_store.update_request(
        request_id=req.id,
        expected_generation=req.generation,
        status="COMPLETED",
    )
    assert updated_valid is True


@pytest.mark.skipif(
    not os.getenv("SHIFTGUARD_TEST_POSTGRES_URL"),
    reason="PostgreSQL URL not configured in SHIFTGUARD_TEST_POSTGRES_URL",
)
def test_postgres_persistence():
    from sqlalchemy.engine import make_url

    pg = os.environ["SHIFTGUARD_TEST_POSTGRES_URL"]
    admin = create_engine(pg, connect_args={"connect_timeout": 3})
    schema = "test_agent_persist_" + uuid4().hex
    with admin.begin() as c:
        c.execute(text(f'CREATE SCHEMA "{schema}"'))

    base_url = make_url(pg)
    url = base_url.update_query_dict({"options": f"-csearch_path={schema}"}).render_as_string(hide_password=False)
    settings = Settings(SHIFTGUARD_DB_URL=url, environment="hosted")

    try:
        upgrade_database(settings)
        engine = create_engine(url)
        store = AgentStore(engine)

        uid = uuid4().hex[:8]
        req, is_new = store.create_or_get_request(
            session_id=f"sess_pg_{uid}",
            intent_key=f"intent_pg_{uid}",
            canonical_body_hash=f"hash_pg_{uid}",
            prompt="PostgreSQL persistence test",
        )
        assert is_new is True
        assert req.id.startswith("req_")

        loaded = store.get_request(req.id)
        assert loaded is not None
        assert loaded.id == req.id
    finally:
        with admin.begin() as c:
            c.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()
