"""Preserve the accepted provider call-ID byte limit in durable columns.

Revision ID: 0011_gate6_call_id_capacity
Revises: 0010_gate6_protocol_hardening
"""

from alembic import op
import sqlalchemy as sa


revision = "0011_gate6_call_id_capacity"
down_revision = "0010_gate6_protocol_hardening"
branch_labels = None
depends_on = None


def _alter_capacity(table: str, column: str, nullable: bool, old: int, new: int) -> None:
    args = dict(
        existing_type=sa.String(length=old), type_=sa.String(length=new),
        existing_nullable=nullable,
    )
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table(table) as batch:
            batch.alter_column(column, **args)
    else:
        op.alter_column(table, column, **args)


def upgrade() -> None:
    _alter_capacity("agent_requests", "active_tool_call_id", True, old=64, new=256)
    _alter_capacity("agent_tool_executions", "tool_call_id", False, old=64, new=256)


def downgrade() -> None:
    bind = op.get_bind()
    oversized = []
    for table, column in (
        ("agent_requests", "active_tool_call_id"),
        ("agent_tool_executions", "tool_call_id"),
    ):
        if bind.execute(sa.text(
            f"SELECT 1 FROM {table} WHERE length({column}) > 64 LIMIT 1"
        )).first():
            oversized.append(f"{table}.{column}")
    if oversized:
        names = ", ".join(oversized)
        raise RuntimeError(
            "Cannot downgrade call-ID capacity to 64 characters while longer values exist in "
            f"{names}; preserve the values or migrate them explicitly before downgrading."
        )

    _alter_capacity("agent_tool_executions", "tool_call_id", False, old=256, new=64)
    _alter_capacity("agent_requests", "active_tool_call_id", True, old=256, new=64)
