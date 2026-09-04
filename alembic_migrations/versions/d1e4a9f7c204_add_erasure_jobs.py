"""Add durable pseudonymous erasure job records.

Revision ID: d1e4a9f7c204
Revises: c39f6e8a14b5
Create Date: 2026-09-01
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "d1e4a9f7c204"
down_revision = "c39f6e8a14b5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "erasure_jobs",
        sa.Column("subject_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("store_results", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("error_code", sa.String(length=96), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("audit_note", sa.Text(), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_erasure_jobs")),
    )
    op.create_index(op.f("ix_erasure_jobs_subject_hash"), "erasure_jobs", ["subject_hash"])
    op.create_index(op.f("ix_erasure_jobs_status"), "erasure_jobs", ["status"])


def downgrade() -> None:
    op.drop_index(op.f("ix_erasure_jobs_status"), table_name="erasure_jobs")
    op.drop_index(op.f("ix_erasure_jobs_subject_hash"), table_name="erasure_jobs")
    op.drop_table("erasure_jobs")
