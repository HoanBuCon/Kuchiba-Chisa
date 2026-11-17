"""Add role assignments and the account authorization version (IAM-001, IAM-003).

Additive only: existing accounts start at authz_ver 1 and have no assignments.

Revision ID: c4d7a1e92b58
Revises: b3e8c1f5a926
Create Date: 2026-11-17
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "c4d7a1e92b58"
down_revision = "b3e8c1f5a926"
branch_labels = None
depends_on = None

ACTOR_LENGTH = 64


def upgrade() -> None:
    op.add_column(
        "accounts",
        sa.Column("authz_ver", sa.Integer(), server_default="1", nullable=False),
    )
    op.create_table(
        "role_assignments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("granted_by", sa.String(ACTOR_LENGTH), nullable=False),
        sa.Column(
            "granted_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by", sa.String(ACTOR_LENGTH), nullable=True),
        sa.Column("revoke_reason", sa.Text(), nullable=True),
        sa.CheckConstraint("role IN ('chia_con', 'admin')", name="ck_role_assignments_role"),
        sa.CheckConstraint(
            "length(btrim(reason)) > 0", name="ck_role_assignments_reason_not_blank"
        ),
    )
    op.create_index("ix_role_assignments_account", "role_assignments", ["account_id"])
    op.create_index(
        "uq_role_assignments_live",
        "role_assignments",
        ["account_id", "role"],
        unique=True,
        postgresql_where=sa.text("revoked_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_table("role_assignments")
    op.drop_column("accounts", "authz_ver")
