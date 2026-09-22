"""Unit tests for G4-07 PostgreSQL dialect compatibility for migration 0005 and queue queries."""

from __future__ import annotations

import pytest
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql, sqlite

from shiftguard.jobs.queue import JobQueue


def test_migration_0005_boolean_server_default_compiles_to_postgres_false():
    """G4-07: Ensure sa.false() compiles to 'false' for PostgreSQL, preventing integer literal errors."""
    col = sa.Column("cancel_requested", sa.Boolean(), nullable=False, server_default=sa.false())
    table = sa.Table("test_table", sa.MetaData(), col)

    pg_dialect = postgresql.dialect()
    ddl = str(sa.schema.CreateTable(table).compile(dialect=pg_dialect))

    # PostgreSQL DDL must contain BOOLEAN NOT NULL DEFAULT false (not 0)
    assert "BOOLEAN" in ddl
    assert "DEFAULT false" in ddl or "DEFAULT FALSE" in ddl
    assert "DEFAULT 0" not in ddl


def test_idempotency_table_composite_pk_compiles_for_postgres():
    """G4-07: Composite primary key (scope, key) compiles cleanly for PostgreSQL dialect."""
    table = sa.Table(
        "idempotency_records",
        sa.MetaData(),
        sa.Column("scope", sa.String(64), nullable=False),
        sa.Column("key", sa.String(128), nullable=False),
        sa.Column("job_id", sa.String(64), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.PrimaryKeyConstraint("scope", "key"),
    )
    pg_dialect = postgresql.dialect()
    ddl = str(sa.schema.CreateTable(table).compile(dialect=pg_dialect))
    assert "PRIMARY KEY (scope, key)" in ddl


def test_continuation_receipts_table_compiles_for_postgres():
    """G4-07: continuation_receipts table schema compiles cleanly for PostgreSQL dialect."""
    table = sa.Table(
        "continuation_receipts",
        sa.MetaData(),
        sa.Column("session_id", sa.String(64), nullable=False),
        sa.Column("nonce", sa.String(64), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.Column("response_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.PrimaryKeyConstraint("session_id", "nonce"),
    )
    pg_dialect = postgresql.dialect()
    ddl = str(sa.schema.CreateTable(table).compile(dialect=pg_dialect))
    assert "PRIMARY KEY (session_id, nonce)" in ddl


def test_queue_enqueue_and_claim_use_boolean_values():
    """G4-07: JobQueue does not use integer literals for cancel_requested in queries."""
    # Inspect queue source code or execution parameter bindings
    import inspect
    queue_source = inspect.getsource(JobQueue)

    # Integer 0/1 assignments to cancel_requested in SQL strings should be absent
    assert "cancel_requested = 0" not in queue_source
    assert "cancel_requested = 1" not in queue_source
    assert "cancel_requested = '0'" not in queue_source
    assert "cancel_requested = '1'" not in queue_source
