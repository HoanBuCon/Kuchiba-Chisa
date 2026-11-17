"""Add Admin TOTP factors, recovery codes and step-up records (SEC-ADM-002, SEC-ADM-006).

Additive only: no existing table changes.

Revision ID: d5a2f7b31c86
Revises: d5e2b8f4a173
Create Date: 2026-11-17
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "d5a2f7b31c86"
down_revision = "d5e2b8f4a173"
branch_labels = None
depends_on = None

DIGEST_LENGTH = 64


def _account_fk() -> sa.ForeignKey:
    return sa.ForeignKey("accounts.id", ondelete="CASCADE")


def upgrade() -> None:
    op.create_table(
        "admin_mfa_factors",
        sa.Column("account_id", postgresql.UUID(as_uuid=True), _account_fk(), primary_key=True),
        sa.Column("secret_sealed", sa.Text(), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_step", sa.BigInteger(), nullable=True),
        sa.Column("failed_attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_table(
        "admin_recovery_codes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), _account_fk(), nullable=False),
        sa.Column("code_digest", sa.String(DIGEST_LENGTH), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_admin_recovery_codes_account_digest",
        "admin_recovery_codes",
        ["account_id", "code_digest"],
        unique=True,
    )
    op.create_table(
        "admin_step_ups",
        sa.Column("session_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), _account_fk(), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("admin_step_ups")
    op.drop_table("admin_recovery_codes")
    op.drop_table("admin_mfa_factors")
