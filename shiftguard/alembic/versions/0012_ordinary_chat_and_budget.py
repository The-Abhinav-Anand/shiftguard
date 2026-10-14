"""Add durable general chat receipts and the ordinary usage ledger.

Revision ID: 0012_ordinary_chat_and_budget
Revises: 0011_gate6_call_id_capacity
"""

from alembic import op
import sqlalchemy as sa


revision = "0012_ordinary_chat_and_budget"
down_revision = "0011_gate6_call_id_capacity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "shiftguard_chat_conversations",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("session_id", sa.String(length=128), nullable=False),
        sa.Column("pending_receipt_id", sa.String(length=32), nullable=True),
        sa.Column("created_at_utc", sa.String(length=32), nullable=False),
        sa.Column("updated_at_utc", sa.String(length=32), nullable=False),
    )
    op.create_index(
        "ix_shiftguard_chat_conversations_session_id",
        "shiftguard_chat_conversations",
        ["session_id"],
    )
    op.create_table(
        "shiftguard_chat_messages",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column(
            "conversation_id",
            sa.String(length=64),
            sa.ForeignKey("shiftguard_chat_conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=9), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at_utc", sa.String(length=32), nullable=False),
        sa.UniqueConstraint(
            "conversation_id", "ordinal", name="uq_shiftguard_chat_message_order"
        ),
    )
    op.create_index(
        "ix_shiftguard_chat_messages_conversation_id",
        "shiftguard_chat_messages",
        ["conversation_id", "ordinal"],
    )
    op.create_table(
        "shiftguard_chat_receipts",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("session_id", sa.String(length=128), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "conversation_id",
            sa.String(length=64),
            sa.ForeignKey("shiftguard_chat_conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_message_id",
            sa.String(length=32),
            sa.ForeignKey("shiftguard_chat_messages.id"),
            nullable=False,
        ),
        sa.Column(
            "assistant_message_id",
            sa.String(length=32),
            sa.ForeignKey("shiftguard_chat_messages.id"),
            nullable=True,
        ),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("response_json", sa.Text(), nullable=True),
        sa.Column("created_at_utc", sa.String(length=32), nullable=False),
        sa.Column("completed_at_utc", sa.String(length=32), nullable=True),
        sa.UniqueConstraint(
            "session_id", "idempotency_key", name="uq_shiftguard_chat_receipt_idempotency"
        ),
    )
    op.create_index(
        "ix_shiftguard_chat_receipts_conversation_id",
        "shiftguard_chat_receipts",
        ["conversation_id"],
    )

    op.create_table(
        "ordinary_budget_daily",
        sa.Column("namespace", sa.String(length=32), nullable=False),
        sa.Column("utc_day", sa.String(length=10), nullable=False),
        sa.Column("source_digest", sa.String(length=64), nullable=False),
        sa.Column("policy_digest", sa.String(length=64), nullable=False),
        sa.Column("max_calls", sa.Integer(), nullable=False),
        sa.Column("max_tokens", sa.Integer(), nullable=False),
        sa.Column("calls_used", sa.Integer(), nullable=False),
        sa.Column("tokens_committed", sa.Integer(), nullable=False),
        sa.Column("halted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("halt_reason", sa.String(length=32), nullable=True),
        sa.PrimaryKeyConstraint("namespace", "utc_day"),
    )
    op.create_table(
        "ordinary_budget_calls",
        sa.Column("reservation_id", sa.String(length=32), primary_key=True),
        sa.Column("namespace", sa.String(length=32), nullable=False),
        sa.Column("utc_day", sa.String(length=10), nullable=False),
        sa.Column("created_at_utc", sa.String(length=32), nullable=False),
        sa.Column("input_sha256", sa.String(length=64), nullable=False),
        sa.Column("input_token_bound", sa.Integer(), nullable=False),
        sa.Column("output_token_bound", sa.Integer(), nullable=False),
        sa.Column("reserved_tokens", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("failure_kind", sa.String(length=32), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
        sa.Column("total_tokens", sa.Integer(), nullable=True),
        sa.Column("provider_request_id_sha256", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(
            ["namespace", "utc_day"],
            ["ordinary_budget_daily.namespace", "ordinary_budget_daily.utc_day"],
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_ordinary_budget_calls_day_status",
        "ordinary_budget_calls",
        ["namespace", "utc_day", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_ordinary_budget_calls_day_status", table_name="ordinary_budget_calls")
    op.drop_table("ordinary_budget_calls")
    op.drop_table("ordinary_budget_daily")
    op.drop_index(
        "ix_shiftguard_chat_receipts_conversation_id",
        table_name="shiftguard_chat_receipts",
    )
    op.drop_table("shiftguard_chat_receipts")
    op.drop_index(
        "ix_shiftguard_chat_messages_conversation_id",
        table_name="shiftguard_chat_messages",
    )
    op.drop_table("shiftguard_chat_messages")
    op.drop_index(
        "ix_shiftguard_chat_conversations_session_id",
        table_name="shiftguard_chat_conversations",
    )
    op.drop_table("shiftguard_chat_conversations")
