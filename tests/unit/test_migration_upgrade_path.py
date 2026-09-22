"""Unit tests for database migration upgrade path from 0005 to 0006."""

from __future__ import annotations

import json
from pathlib import Path
import pytest
from sqlalchemy import create_engine, text
from alembic import command
from alembic.config import Config

from shiftguard.migrations import get_alembic_config
from shiftguard.settings import Settings


def test_upgrade_from_0005_to_0006(tmp_path):
    """R2-06: Existing databases stamped at 0005 upgrade cleanly to 0006 with preserved rows and backfills."""
    db_file = tmp_path / "upgrade_test.db"
    db_url = f"sqlite:///{db_file}"
    settings = Settings(SHIFTGUARD_DB_URL=db_url)
    config = get_alembic_config(settings)

    # 1. Upgrade only to 0005
    engine = create_engine(db_url)
    with engine.connect() as conn:
        config.attributes["connection"] = conn
        command.upgrade(config, "0005_gate4_jobs_and_continuation")

    # 2. Insert representative rows in 0005 schema
    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO agent_sessions (
                    id, status, active_nonce, required_job_ids_json, state_json, created_at, updated_at
                ) VALUES (
                    'sess-001', 'active', 'nonce-001', '[]', '{}', '2026-09-18T12:00:00Z', '2026-09-18T12:00:00Z'
                )
            """)
        )
        conn.execute(
            text("""
                INSERT INTO jobs (
                    id, session_id, payload_hash, status, request_params_json, attempt, max_attempts, cancel_requested, created_at
                ) VALUES (
                    'job-001', 'sess-001', 'hash-001', 'queued', '{}', 0, 3, 0, '2026-09-18T12:00:00Z'
                )
            """)
        )
        # Old idempotency_records has key as single primary key (no scope column)
        conn.execute(
            text("""
                INSERT INTO idempotency_records (
                    key, payload_hash, job_id, response_code, response_json, created_at
                ) VALUES (
                    'idem-key-1', 'hash-001', 'job-001', 202, '{"job_id": "job-001"}', '2026-09-18T12:00:00Z'
                )
            """)
        )
        # Standalone job without session
        conn.execute(
            text("""
                INSERT INTO jobs (
                    id, session_id, payload_hash, status, request_params_json, attempt, max_attempts, cancel_requested, created_at
                ) VALUES (
                    'job-global', NULL, 'hash-global', 'queued', '{}', 0, 3, 0, '2026-09-18T12:00:00Z'
                )
            """)
        )
        conn.execute(
            text("""
                INSERT INTO idempotency_records (
                    key, payload_hash, job_id, response_code, response_json, created_at
                ) VALUES (
                    'idem-key-global', 'hash-global', 'job-global', 202, '{"job_id": "job-global"}', '2026-09-18T12:00:00Z'
                )
            """)
        )

    # 3. Upgrade to head (0006)
    with engine.connect() as conn:
        config.attributes["connection"] = conn
        command.upgrade(config, "head")

    # 4. Verify preserved rows and backfilled columns
    with engine.connect() as conn:
        # Check idempotency record for job with session has scope = 'sess-001'
        idem_row = conn.execute(
            text("SELECT scope, key, payload_hash, job_id FROM idempotency_records WHERE key = 'idem-key-1'")
        ).mappings().fetchone()
        assert idem_row is not None
        assert idem_row["scope"] == "sess-001"
        assert idem_row["job_id"] == "job-001"

        # Check idempotency record for job without session has scope = 'global'
        idem_global = conn.execute(
            text("SELECT scope, key, payload_hash, job_id FROM idempotency_records WHERE key = 'idem-key-global'")
        ).mappings().fetchone()
        assert idem_global is not None
        assert idem_global["scope"] == "global"
        assert idem_global["job_id"] == "job-global"

        # Check inserting a scoped idempotency record with same key but different scope succeeds
        with engine.begin() as write_conn:
            write_conn.execute(
                text("""
                    INSERT INTO idempotency_records (
                        scope, key, payload_hash, job_id, response_code, response_json, created_at
                    ) VALUES (
                        'sess-002', 'idem-key-1', 'hash-002', 'job-002', 202, '{"job_id": "job-002"}', '2026-09-18T12:05:00Z'
                    )
                """)
            )

        scoped_row = conn.execute(
            text("SELECT scope, key, job_id FROM idempotency_records WHERE scope = 'sess-002' AND key = 'idem-key-1'")
        ).mappings().fetchone()
        assert scoped_row is not None
        assert scoped_row["job_id"] == "job-002"

        # Check continuation_receipts table exists
        receipts_count = conn.execute(text("SELECT COUNT(*) FROM continuation_receipts")).scalar()
        assert receipts_count == 0

        # Check capability_token column exists in agent_sessions and legacy session is marked expired
        session_row = conn.execute(
            text("SELECT id, status, capability_token FROM agent_sessions WHERE id = 'sess-001'")
        ).mappings().fetchone()
        assert session_row is not None
        assert "capability_token" in session_row
        assert session_row["status"] == "expired"
        from shiftguard.jobs.models import SessionStatus
        assert SessionStatus(session_row["status"]) == SessionStatus.EXPIRED

        # Check publication table has new linkage columns
        pub_cols = [c[1] for c in conn.execute(text("PRAGMA table_info(experiment_publications)")).fetchall()]
        assert "job_id" in pub_cols
        assert "lease_expires_at" in pub_cols
        assert "prepared_payload_json" in pub_cols
        assert "prepared_audit_json" in pub_cols
        assert "attempt" in pub_cols
        assert "fencing_token" in pub_cols

    engine.dispose()
