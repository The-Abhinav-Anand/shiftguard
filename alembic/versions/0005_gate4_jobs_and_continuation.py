"""Add jobs, job_events, agent_sessions, and idempotency_records for Gate 4 durable runtime."""

from alembic import op
import sqlalchemy as sa


revision = "0005_gate4_jobs_and_continuation"
down_revision = "0004_publication_records"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "jobs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("experiment_id", sa.String(length=64), nullable=True, index=True),
        sa.Column("session_id", sa.String(length=36), nullable=True, index=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True, index=True),
        sa.Column("payload_hash", sa.String(length=64), nullable=False, index=True),
        sa.Column("status", sa.String(length=20), nullable=False, index=True, server_default="queued"),
        sa.Column("request_params_json", sa.Text(), nullable=False),
        sa.Column("worker_id", sa.String(length=64), nullable=True),
        sa.Column("fencing_token", sa.String(length=36), nullable=True),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("lease_expires_at", sa.String(length=32), nullable=True),
        sa.Column("heartbeat_at", sa.String(length=32), nullable=True),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("error_json", sa.Text(), nullable=True),
        sa.Column("result_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.String(length=32), nullable=False, index=True),
        sa.Column("started_at", sa.String(length=32), nullable=True),
        sa.Column("completed_at", sa.String(length=32), nullable=True),
    )

    op.create_table(
        "job_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("job_id", sa.String(length=36), nullable=False, index=True),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("fencing_token", sa.String(length=36), nullable=True),
        sa.Column("details_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.String(length=32), nullable=False),
    )

    op.create_table(
        "agent_sessions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("status", sa.String(length=32), nullable=False, index=True),
        sa.Column("active_nonce", sa.String(length=64), nullable=False),
        sa.Column("required_job_ids_json", sa.Text(), nullable=False),
        sa.Column("state_json", sa.Text(), nullable=False),
        sa.Column("result_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.Column("updated_at", sa.String(length=32), nullable=False),
    )

    op.create_table(
        "idempotency_records",
        sa.Column("key", sa.String(length=128), primary_key=True),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("job_id", sa.String(length=36), nullable=False, index=True),
        sa.Column("response_code", sa.Integer(), nullable=False),
        sa.Column("response_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.String(length=32), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("idempotency_records")
    op.drop_table("agent_sessions")
    op.drop_table("job_events")
    op.drop_table("jobs")
