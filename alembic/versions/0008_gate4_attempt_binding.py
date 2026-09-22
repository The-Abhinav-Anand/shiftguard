"""Gate 4 attempt binding: add attempt and fencing_token to experiment_publications.

Revision ID: 0008_gate4_attempt_binding
Revises: 0007_gate4_r4_hardening
Create Date: 2026-09-19 12:00:00.000000

Adds attempt and fencing_token columns to experiment_publications so that
prepared publications are strictly bound to the specific preparing job attempt.
Recovery and finalization validate these against the active job attempt.
"""

from alembic import op
import sqlalchemy as sa


revision = "0008_gate4_attempt_binding"
down_revision = "0007_gate4_r4_hardening"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    pub_cols = [c["name"] for c in inspector.get_columns("experiment_publications")]
    if "attempt" not in pub_cols:
        op.add_column("experiment_publications", sa.Column("attempt", sa.Integer(), nullable=True))
    if "fencing_token" not in pub_cols:
        op.add_column("experiment_publications", sa.Column("fencing_token", sa.String(length=64), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    pub_cols = [c["name"] for c in inspector.get_columns("experiment_publications")]
    if "fencing_token" in pub_cols:
        op.drop_column("experiment_publications", "fencing_token")
    if "attempt" in pub_cols:
        op.drop_column("experiment_publications", "attempt")
