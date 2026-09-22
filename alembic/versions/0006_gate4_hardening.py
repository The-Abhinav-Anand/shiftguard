"""Add Gate 4 hardening columns, scoped idempotency, continuation receipts, and publication linkage.

Revision ID: 0006_gate4_hardening
Revises: 0005_gate4_jobs_and_continuation
Create Date: 2026-09-18 19:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0006_gate4_hardening"
down_revision = "0005_gate4_jobs_and_continuation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    # 1. Migrate idempotency_records to composite PK (scope, key) if scope is not present
    idemp_cols = [c["name"] for c in inspector.get_columns("idempotency_records")]
    if "scope" not in idemp_cols:
        if dialect == "sqlite":
            op.execute("DROP INDEX IF EXISTS ix_idempotency_records_job_id")
            op.rename_table("idempotency_records", "idempotency_records_old")
            op.create_table(
                "idempotency_records",
                sa.Column("scope", sa.String(length=64), primary_key=True, server_default="global"),
                sa.Column("key", sa.String(length=128), primary_key=True),
                sa.Column("payload_hash", sa.String(length=64), nullable=False),
                sa.Column("job_id", sa.String(length=36), nullable=False, index=True),
                sa.Column("response_code", sa.Integer(), nullable=False),
                sa.Column("response_json", sa.Text(), nullable=False),
                sa.Column("created_at", sa.String(length=32), nullable=False),
            )
            op.execute(
                """
                INSERT INTO idempotency_records (scope, key, payload_hash, job_id, response_code, response_json, created_at)
                SELECT 
                    COALESCE(
                        (SELECT session_id FROM jobs WHERE jobs.id = idempotency_records_old.job_id AND jobs.session_id IS NOT NULL),
                        'global'
                    ),
                    key, payload_hash, job_id, response_code, response_json, created_at 
                FROM idempotency_records_old
                """
            )
            op.drop_table("idempotency_records_old")
        else:
            op.add_column("idempotency_records", sa.Column("scope", sa.String(length=64), nullable=True))
            op.execute(
                """
                UPDATE idempotency_records 
                SET scope = COALESCE(
                    (SELECT session_id FROM jobs WHERE jobs.id = idempotency_records.job_id AND jobs.session_id IS NOT NULL),
                    'global'
                )
                WHERE scope IS NULL
                """
            )
            op.alter_column("idempotency_records", "scope", nullable=False, server_default="global")
            op.drop_constraint("idempotency_records_pkey", "idempotency_records", type_="primary")
            op.create_primary_key("idempotency_records_pkey", "idempotency_records", ["scope", "key"])

    # 2. Create continuation_receipts table if not present
    if "continuation_receipts" not in tables:
        op.create_table(
            "continuation_receipts",
            sa.Column("session_id", sa.String(length=36), nullable=False, index=True),
            sa.Column("nonce", sa.String(length=64), primary_key=True),
            sa.Column("status_code", sa.Integer(), nullable=False),
            sa.Column("response_json", sa.Text(), nullable=False),
            sa.Column("created_at", sa.String(length=32), nullable=False),
        )

    # 3. Add capability_token to agent_sessions if not present, and mark legacy sessions expired
    sess_cols = [c["name"] for c in inspector.get_columns("agent_sessions")]
    if "capability_token" not in sess_cols:
        op.add_column("agent_sessions", sa.Column("capability_token", sa.String(length=64), nullable=True))
        op.execute("UPDATE agent_sessions SET status = 'expired' WHERE capability_token IS NULL")

    # 4. Add linkage and recovery columns to experiment_publications if not present
    pub_cols = [c["name"] for c in inspector.get_columns("experiment_publications")]
    if "job_id" not in pub_cols:
        op.add_column("experiment_publications", sa.Column("job_id", sa.String(length=36), nullable=True))
        op.create_index("ix_experiment_publications_job_id", "experiment_publications", ["job_id"])
    if "lease_expires_at" not in pub_cols:
        op.add_column("experiment_publications", sa.Column("lease_expires_at", sa.String(length=32), nullable=True))
    if "prepared_payload_json" not in pub_cols:
        op.add_column("experiment_publications", sa.Column("prepared_payload_json", sa.Text(), nullable=True))
    if "prepared_audit_json" not in pub_cols:
        op.add_column("experiment_publications", sa.Column("prepared_audit_json", sa.Text(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    pub_cols = [c["name"] for c in inspector.get_columns("experiment_publications")]
    if "job_id" in pub_cols:
        op.drop_index("ix_experiment_publications_job_id", table_name="experiment_publications")
        op.drop_column("experiment_publications", "prepared_audit_json")
        op.drop_column("experiment_publications", "prepared_payload_json")
        op.drop_column("experiment_publications", "lease_expires_at")
        op.drop_column("experiment_publications", "job_id")

    sess_cols = [c["name"] for c in inspector.get_columns("agent_sessions")]
    if "capability_token" in sess_cols:
        op.drop_column("agent_sessions", "capability_token")

    if "continuation_receipts" in tables:
        op.drop_table("continuation_receipts")

    idemp_cols = [c["name"] for c in inspector.get_columns("idempotency_records")]
    if "scope" in idemp_cols:
        if dialect == "sqlite":
            op.execute("DROP INDEX IF EXISTS ix_idempotency_records_job_id")
            op.rename_table("idempotency_records", "idempotency_records_old")
            op.create_table(
                "idempotency_records",
                sa.Column("key", sa.String(length=128), primary_key=True),
                sa.Column("payload_hash", sa.String(length=64), nullable=False),
                sa.Column("job_id", sa.String(length=36), nullable=False, index=True),
                sa.Column("response_code", sa.Integer(), nullable=False),
                sa.Column("response_json", sa.Text(), nullable=False),
                sa.Column("created_at", sa.String(length=32), nullable=False),
            )
            op.execute(
                "INSERT INTO idempotency_records (key, payload_hash, job_id, response_code, response_json, created_at) "
                "SELECT key, payload_hash, job_id, response_code, response_json, created_at FROM idempotency_records_old"
            )
            op.drop_table("idempotency_records_old")
        else:
            op.drop_constraint("idempotency_records_pkey", "idempotency_records", type_="primary")
            op.create_primary_key("idempotency_records_pkey", "idempotency_records", ["key"])
            op.drop_column("idempotency_records", "scope")
