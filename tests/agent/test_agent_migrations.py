"""Tests for Gate 6 database schema migration 0009_gate6_agent_runtime."""

from __future__ import annotations

import os
from uuid import uuid4
import pytest
from sqlalchemy import create_engine, inspect, text

from shiftguard.migrations import upgrade_database
from shiftguard.settings import Settings


def test_migration_upgrades_cleanly_on_sqlite(tmp_path):
    db_file = tmp_path / "test_migration_0009.db"
    settings = Settings(SHIFTGUARD_DB_URL=f"sqlite:///{db_file}")

    # Upgrade to head
    upgrade_database(settings)

    engine = create_engine(f"sqlite:///{db_file}")
    inspector = inspect(engine)
    tables = inspector.get_table_names()

    # Verify Gate 6 tables exist
    assert "agent_requests" in tables
    assert "agent_tool_executions" in tables
    assert "agent_continuation_receipts" in tables

    # Verify key columns in agent_requests
    cols = {c["name"]: c for c in inspector.get_columns("agent_requests")}
    assert "id" in cols
    assert "session_id" in cols
    assert "intent_key" in cols
    assert "canonical_body_hash" in cols
    assert "status" in cols
    assert "generation" in cols
    assert "turn_count" in cols
    assert "call_count" in cols
    assert "repair_count" in cols
    assert "active_job_id" in cols

    # Verify unique constraint on (session_id, intent_key)
    uqs = inspector.get_unique_constraints("agent_requests")
    uq_col_sets = [set(u["column_names"]) for u in uqs]
    assert {"session_id", "intent_key"} in uq_col_sets


@pytest.mark.skipif(
    not os.getenv("SHIFTGUARD_TEST_POSTGRES_URL"),
    reason="PostgreSQL URL not configured in SHIFTGUARD_TEST_POSTGRES_URL",
)
def test_migration_upgrades_cleanly_on_postgres():
    from sqlalchemy.engine import make_url

    pg = os.environ["SHIFTGUARD_TEST_POSTGRES_URL"]
    admin = create_engine(pg, connect_args={"connect_timeout": 3})
    schema = "test_agent_mig_" + uuid4().hex
    with admin.begin() as c:
        c.execute(text(f'CREATE SCHEMA "{schema}"'))

    base_url = make_url(pg)
    url = base_url.update_query_dict({"options": f"-csearch_path={schema}"}).render_as_string(hide_password=False)
    settings = Settings(SHIFTGUARD_DB_URL=url, environment="hosted")

    try:
        upgrade_database(settings)
        engine = create_engine(url)
        inspector = inspect(engine)
        tables = inspector.get_table_names()

        assert "agent_requests" in tables
        assert "agent_tool_executions" in tables
        assert "agent_continuation_receipts" in tables
    finally:
        with admin.begin() as c:
            c.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()
