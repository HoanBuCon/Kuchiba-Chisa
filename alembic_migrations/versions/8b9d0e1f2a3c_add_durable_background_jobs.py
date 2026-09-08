"""Add the PostgreSQL transactional outbox and durable job state.

Revision ID: 8b9d0e1f2a3c
Revises: 7a8c9d0e1f2b
Create Date: 2026-09-08
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "8b9d0e1f2a3c"
down_revision = "7a8c9d0e1f2b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "durable_background_jobs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("job_type", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("payload_version", sa.Integer(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("principal_id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_owner", sa.String(length=128), nullable=True),
        sa.Column("lease_token", sa.UUID(), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(length=128), nullable=True),
        sa.Column("last_error_detail", sa.Text(), nullable=True),
        sa.Column("terminal_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replay_count", sa.Integer(), nullable=False),
        sa.Column("last_replayed_by", sa.String(length=128), nullable=True),
        sa.Column("last_replayed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("attempt_count >= 0", name="ck_durable_background_jobs_attempt_count"),
        sa.CheckConstraint(
            "max_attempts BETWEEN 1 AND 10",
            name="ck_durable_background_jobs_max_attempts",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'retry_scheduled', 'succeeded', 'dead_letter')",
            name="ck_durable_background_jobs_status",
        ),
        sa.ForeignKeyConstraint(["principal_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key"),
    )
    op.create_index(
        "ix_durable_background_jobs_principal_id",
        "durable_background_jobs",
        ["principal_id"],
    )
    op.create_index(
        "ix_durable_background_jobs_tenant_id",
        "durable_background_jobs",
        ["tenant_id"],
    )
    op.create_index(
        "ix_durable_jobs_available",
        "durable_background_jobs",
        ["status", "available_at"],
    )
    op.create_index(
        "ix_durable_jobs_lease_expiry",
        "durable_background_jobs",
        ["status", "lease_expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_durable_jobs_lease_expiry", table_name="durable_background_jobs")
    op.drop_index("ix_durable_jobs_available", table_name="durable_background_jobs")
    op.drop_index("ix_durable_background_jobs_tenant_id", table_name="durable_background_jobs")
    op.drop_index("ix_durable_background_jobs_principal_id", table_name="durable_background_jobs")
    op.drop_table("durable_background_jobs")
