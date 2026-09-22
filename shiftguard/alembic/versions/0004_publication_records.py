"""Add publication records table for recoverable two-phase artifact publication."""

from alembic import op
import sqlalchemy as sa


revision = "0004_publication_records"
down_revision = "0003_gate1_execution_audit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "experiment_publications",
        sa.Column("generation_id", sa.String(length=36), primary_key=True),
        sa.Column("experiment_id", sa.String(length=64), nullable=False, index=True),
        sa.Column("full_digest", sa.String(length=64), nullable=False),
        sa.Column("execution_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("manifest_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.Column("updated_at", sa.String(length=32), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("experiment_publications")
