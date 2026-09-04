"""Add consented long-term-memory retention settings.

Revision ID: e5f3a7c9d102
Revises: d4f2c8e6a915
Create Date: 2026-09-05
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "e5f3a7c9d102"
down_revision = "d4f2c8e6a915"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Additive privacy metadata only; never alter existing conversations or vectors."""
    op.create_table(
        "user_privacy_preferences",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "long_term_memory_enabled", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("retention_days", sa.Integer(), nullable=True),
        sa.Column("consented_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
        sa.CheckConstraint(
            "retention_days IS NULL OR (retention_days >= 1 AND retention_days <= 365)",
            name="user_privacy_preferences_retention_days",
        ),
    )
    op.create_table(
        "privacy_policy_audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("long_term_memory_enabled", sa.Boolean(), nullable=False),
        sa.Column("retention_days", sa.Integer(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_privacy_policy_audit_events_user_id"),
        "privacy_policy_audit_events",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_privacy_policy_audit_events_user_id"), table_name="privacy_policy_audit_events"
    )
    op.drop_table("privacy_policy_audit_events")
    op.drop_table("user_privacy_preferences")
