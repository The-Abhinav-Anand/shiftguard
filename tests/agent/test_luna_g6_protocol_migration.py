from __future__ import annotations

import shutil
from pathlib import Path

from sqlalchemy import create_engine, inspect, text

from shiftguard.migrations import upgrade_database
from shiftguard.settings import Settings


PROJECT_ROOT = Path(__file__).resolve().parents[2]
HISTORICAL_DB = (
    PROJECT_ROOT.parent / "verification" / "gate6" / "offline-f72afeff-0cad-438f-bccb-157a39b08ef1"
    / "shiftguard.sqlite"
)


def _settings(path: Path) -> Settings:
    return Settings(SHIFTGUARD_DB_URL=f"sqlite:///{path}")


def _counts(engine):
    with engine.connect() as conn:
        tables = set(inspect(conn).get_table_names())
        names = (
            "agent_sessions", "agent_requests", "agent_tool_executions",
            "agent_continuation_receipts", "jobs", "idempotency_records",
            "job_events", "experiments", "experiment_executions", "experiment_publications",
        )
        return {name: conn.execute(text(f"SELECT COUNT(*) FROM {name}")).scalar_one()
                for name in names if name in tables}


def test_luna_g6_protocol_migration_preserves_nonempty_historical_0009(tmp_path):
    assert HISTORICAL_DB.is_file()
    target = tmp_path / "historical-copy.sqlite"
    shutil.copyfile(HISTORICAL_DB, target)
    settings = _settings(target)
    engine = create_engine(settings.db_url)
    try:
        before_counts = _counts(engine)
        with engine.connect() as conn:
            before_req = conn.execute(text("""
                SELECT id, session_id, intent_key, canonical_body_hash, status,
                       generation, turn_count, call_count, active_job_id,
                       messages_json, evidence_refs_json, final_response_json, error_json
                FROM agent_requests ORDER BY id
            """)).all()
            assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "0009_gate6_agent_runtime"
            columns = {c["name"] for c in inspect(conn).get_columns("agent_requests")}
            assert not {"active_nonce", "repair_ledger_json", "pending_tool_calls_json"} & columns
        assert before_counts["agent_requests"] and before_counts["agent_tool_executions"]
        assert before_counts["agent_continuation_receipts"] and before_counts["jobs"]

        upgrade_database(settings)

        with engine.connect() as conn:
            after_req = conn.execute(text("""
                SELECT id, session_id, intent_key, canonical_body_hash, status,
                       generation, turn_count, call_count, active_job_id,
                       messages_json, evidence_refs_json, final_response_json, error_json
                FROM agent_requests ORDER BY id
            """)).all()
            assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "0011_gate6_call_id_capacity"
            columns = {c["name"] for c in inspect(conn).get_columns("agent_requests")}
            assert {
                "active_nonce", "repair_ledger_json", "pending_tool_calls_json",
                "active_nonce_generation", "accepted_decision_json", "pending_cursor",
                "authority_token_hash",
            } <= columns
        assert _counts(engine) == before_counts
        assert after_req == before_req
    finally:
        engine.dispose()


def test_luna_g6_protocol_migration_repairs_expanded_0009_shape(tmp_path):
    target = tmp_path / "expanded-0009.sqlite"
    settings = _settings(target)
    upgrade_database(settings)
    engine = create_engine(settings.db_url)
    try:
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO agent_sessions (id, status, active_nonce, capability_token, required_job_ids_json, state_json, result_json, created_at, updated_at) VALUES ('session-expanded', 'active', 'session-nonce', 'capability', '[]', '{}', NULL, '2026-10-01', '2026-10-01')"))
            conn.execute(text("""
                INSERT INTO agent_requests (
                    id, session_id, intent_key, canonical_body_hash, prompt, status,
                    generation, turn_count, call_count, repair_count, active_job_id,
                    active_tool_call_id, messages_json, evidence_refs_json, created_at, updated_at,
                    active_nonce, repair_ledger_json, pending_tool_calls_json
                ) VALUES (
                    'request-expanded', 'session-expanded', 'intent', 'hash', 'prompt', 'RUNNING',
                    1, 0, 0, 0, NULL, NULL, '[]', '[]', '2026-10-01', '2026-10-01',
                    'stale-nonce', :repair_ledger, '[]'
                )
            """), {"repair_ledger": '{"legacy":0}'})
            conn.execute(text("DROP INDEX IF EXISTS ix_agent_requests_active_nonce"))
            for name in ("active_nonce_generation", "accepted_decision_json", "pending_cursor", "authority_token_hash"):
                conn.execute(text(f"ALTER TABLE agent_requests DROP COLUMN {name}"))
            conn.execute(text("UPDATE alembic_version SET version_num='0009_gate6_agent_runtime'"))

        upgrade_database(settings)

        with engine.connect() as conn:
            row = conn.execute(text("""
                SELECT active_nonce, active_nonce_generation, repair_ledger_json,
                       pending_tool_calls_json, accepted_decision_json, pending_cursor,
                       authority_token_hash
                FROM agent_requests WHERE id='request-expanded'
            """)).one()
            assert row.active_nonce is None
            assert row.active_nonce_generation is None
            assert row.repair_ledger_json == '{"legacy":0}'
            assert row.pending_tool_calls_json == '[]'
            assert row.accepted_decision_json is None and row.pending_cursor == 0
            assert row.authority_token_hash is None
            assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "0011_gate6_call_id_capacity"
    finally:
        engine.dispose()

