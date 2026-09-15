"""Preserve Gate1 execution audit rows separately from immutable content."""

from alembic import op
import sqlalchemy as sa


revision = "0003_gate1_execution_audit"
down_revision = "0002_gate1_experiments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "experiment_executions",
        sa.Column("execution_id", sa.String(length=36), primary_key=True),
        sa.Column("experiment_id", sa.String(length=64), sa.ForeignKey("experiments.id"), nullable=False),
        sa.Column("audit_json", sa.Text(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("experiment_executions")
