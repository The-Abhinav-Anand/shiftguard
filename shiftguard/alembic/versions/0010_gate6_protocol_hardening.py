"""Repair the persisted Gate 6 agent shape and checkpoint the dispatch protocol.

Revision ID: 0010_gate6_protocol_hardening
Revises: 0009_gate6_agent_runtime
Create Date: 2026-10-01 00:00:00.000000
"""

from __future__ import annotations

import secrets

from alembic import op
import sqlalchemy as sa


revision = "0010_gate6_protocol_hardening"
down_revision = "0009_gate6_agent_runtime"
branch_labels = None
depends_on = None


def _columns(bind) -> set[str]:
    return {column["name"] for column in sa.inspect(bind).get_columns("agent_requests")}


def upgrade() -> None:
    bind = op.get_bind()
    if "agent_requests" not in sa.inspect(bind).get_table_names():
        return

    # These three fields were mistakenly added by editing already-applied 0009.
    # Add them here for both the historically stamped and expanded 0009 shape.
    additions = (
        ("active_nonce", sa.Column("active_nonce", sa.String(64), nullable=True)),
        ("repair_ledger_json", sa.Column("repair_ledger_json", sa.Text(), nullable=False, server_default="{}")),
        ("pending_tool_calls_json", sa.Column("pending_tool_calls_json", sa.Text(), nullable=False, server_default="[]")),
        ("active_nonce_generation", sa.Column("active_nonce_generation", sa.Integer(), nullable=True)),
        ("accepted_decision_json", sa.Column("accepted_decision_json", sa.Text(), nullable=True)),
        ("pending_cursor", sa.Column("pending_cursor", sa.Integer(), nullable=False, server_default="0")),
        ("authority_token_hash", sa.Column("authority_token_hash", sa.String(64), nullable=True)),
    )
    for name, column in additions:
        if name not in _columns(bind):
            op.add_column("agent_requests", column)

    columns = _columns(bind)
    if "ix_agent_requests_active_nonce" not in {
        item["name"] for item in sa.inspect(bind).get_indexes("agent_requests")
    }:
        op.create_index("ix_agent_requests_active_nonce", "agent_requests", ["active_nonce"])

    bind.execute(sa.text("UPDATE agent_requests SET repair_ledger_json = '{}' WHERE repair_ledger_json IS NULL"))
    bind.execute(sa.text("UPDATE agent_requests SET pending_tool_calls_json = '[]' WHERE pending_tool_calls_json IS NULL"))
    bind.execute(sa.text("UPDATE agent_requests SET pending_cursor = 0 WHERE pending_cursor IS NULL"))

    # Only WAITING_FOR_JOB with an attached job is a legal nonce-issuance state.
    # Existing issued values survive; rows without one receive a fresh persisted
    # nonce. Stale RUNNING/terminal values from the pre-repair implementation are
    # invalidated because their issuance could not be proven.
    rows = bind.execute(
        sa.text(
            "SELECT id, status, active_job_id, active_nonce, generation "
            "FROM agent_requests"
        )
    ).mappings().all()
    for row in rows:
        status = str(row["status"]).upper()
        if status == "WAITING_FOR_JOB" and row["active_job_id"]:
            nonce = row["active_nonce"] or secrets.token_urlsafe(24)
            bind.execute(
                sa.text(
                    "UPDATE agent_requests SET active_nonce = :nonce, "
                    "active_nonce_generation = COALESCE(active_nonce_generation, generation) "
                    "WHERE id = :id"
                ),
                {"id": row["id"], "nonce": nonce},
            )
        else:
            bind.execute(
                sa.text(
                    "UPDATE agent_requests SET active_nonce = NULL, "
                    "active_nonce_generation = NULL WHERE id = :id"
                ),
                {"id": row["id"]},
            )


def downgrade() -> None:
    bind = op.get_bind()
    if "agent_requests" not in sa.inspect(bind).get_table_names():
        return
    columns = _columns(bind)
    indexes = {item["name"] for item in sa.inspect(bind).get_indexes("agent_requests")}
    if "ix_agent_requests_active_nonce" in indexes:
        op.drop_index("ix_agent_requests_active_nonce", table_name="agent_requests")
    for name in (
        "authority_token_hash",
        "pending_cursor",
        "accepted_decision_json",
        "active_nonce_generation",
        "pending_tool_calls_json",
        "repair_ledger_json",
        "active_nonce",
    ):
        if name in columns:
            op.drop_column("agent_requests", name)
