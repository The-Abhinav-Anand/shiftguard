"""Add agent_requests, agent_tool_executions, and agent_continuation_receipts for Gate 6 agent runtime.

Revision ID: 0009_gate6_agent_runtime
Revises: 0008_gate4_attempt_binding
Create Date: 2026-09-30 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0009_gate6_agent_runtime"
down_revision = "0008_gate4_attempt_binding"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    if "agent_requests" not in tables:
        op.create_table(
            "agent_requests",
            sa.Column("id", sa.String(length=64), primary_key=True),
            sa.Column("session_id", sa.String(length=36), nullable=False, index=True),
            sa.Column("intent_key", sa.String(length=128), nullable=False, index=True),
            sa.Column("canonical_body_hash", sa.String(length=64), nullable=False),
            sa.Column("prompt", sa.Text(), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False, index=True, server_default="RUNNING"),
            sa.Column("generation", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("lease_expires_at", sa.String(length=32), nullable=True),
            sa.Column("worker_id", sa.String(length=64), nullable=True),
            sa.Column("turn_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("call_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("repair_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("active_job_id", sa.String(length=36), nullable=True, index=True),
            sa.Column("active_tool_call_id", sa.String(length=64), nullable=True),
            sa.Column("messages_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("evidence_refs_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("final_response_json", sa.Text(), nullable=True),
            sa.Column("error_json", sa.Text(), nullable=True),
            sa.Column("created_at", sa.String(length=32), nullable=False, index=True),
            sa.Column("updated_at", sa.String(length=32), nullable=False),
            sa.UniqueConstraint("session_id", "intent_key", name="uq_agent_requests_session_intent"),
        )

    if "agent_tool_executions" not in tables:
        op.create_table(
            "agent_tool_executions",
            sa.Column("id", sa.String(length=64), primary_key=True),
            sa.Column("request_id", sa.String(length=64), nullable=False, index=True),
            sa.Column("ordinal", sa.Integer(), nullable=False),
            sa.Column("tool_name", sa.String(length=64), nullable=False),
            sa.Column("tool_call_id", sa.String(length=64), nullable=False),
            sa.Column("arguments_json", sa.Text(), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="PENDING"),
            sa.Column("idempotency_key", sa.String(length=128), nullable=False, index=True),
            sa.Column("job_id", sa.String(length=36), nullable=True, index=True),
            sa.Column("result_json", sa.Text(), nullable=True),
            sa.Column("created_at", sa.String(length=32), nullable=False),
            sa.Column("completed_at", sa.String(length=32), nullable=True),
            sa.UniqueConstraint("request_id", "ordinal", name="uq_agent_tool_executions_request_ordinal"),
        )

    if "agent_continuation_receipts" not in tables:
        op.create_table(
            "agent_continuation_receipts",
            sa.Column("id", sa.String(length=64), primary_key=True),
            sa.Column("request_id", sa.String(length=64), nullable=False, index=True),
            sa.Column("nonce", sa.String(length=64), nullable=False, index=True),
            sa.Column("status_code", sa.Integer(), nullable=False),
            sa.Column("response_json", sa.Text(), nullable=False),
            sa.Column("created_at", sa.String(length=32), nullable=False),
            sa.UniqueConstraint("request_id", "nonce", name="uq_agent_continuation_receipts_request_nonce"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    if "agent_continuation_receipts" in tables:
        op.drop_table("agent_continuation_receipts")
    if "agent_tool_executions" in tables:
        op.drop_table("agent_tool_executions")
    if "agent_requests" in tables:
        op.drop_table("agent_requests")
