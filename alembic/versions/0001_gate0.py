"""Create Gate0 bootstrap schema."""

from alembic import op
import sqlalchemy as sa


revision = "0001_gate0"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "application_metadata",
        sa.Column("key", sa.String(length=100), primary_key=True),
        sa.Column("value", sa.String(length=500), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("application_metadata")
