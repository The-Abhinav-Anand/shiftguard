"""Gate 4 R4 hardening checkpoint — behavioral fixes, no schema changes.

Revision ID: 0007_gate4_r4_hardening
Revises: 0006_gate4_hardening
Create Date: 2026-09-19 04:00:00.000000

This migration is a forward-only checkpoint marking the R4 remediation.
All four fixes (R4-01 through R4-04) are behavioral changes in the
application layer; the existing schema already has all required columns.
"""

from alembic import op
import sqlalchemy as sa


revision = "0007_gate4_r4_hardening"
down_revision = "0006_gate4_hardening"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # No schema changes; this revision exists to mark the R4 behavioral
    # hardening checkpoint in the migration chain.
    pass


def downgrade() -> None:
    pass
