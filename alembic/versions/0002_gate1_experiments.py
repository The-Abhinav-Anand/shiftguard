"""Create Gate1 experiment persistence."""

from alembic import op
import sqlalchemy as sa


revision = "0002_gate1_experiments"
down_revision = "0001_gate0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "experiments",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("content_hashes_json", sa.Text(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("experiments")
