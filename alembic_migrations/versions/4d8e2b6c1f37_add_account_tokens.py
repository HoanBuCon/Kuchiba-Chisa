"""Add single-use account tokens for e-mail verification and password reset.

Additive only. Raw tokens are never stored: ``token_hash`` holds SHA-256. Existing
accounts keep ``email_verified`` as-is (password accounts created before this
revision were never verified and must verify by e-mail before signing in).

Revision ID: 4d8e2b6c1f37
Revises: 1a7c3e5f9b20
Create Date: 2026-10-05
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "4d8e2b6c1f37"
down_revision = "1a7c3e5f9b20"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "account_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("purpose", sa.String(length=32), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "purpose IN ('verify_email', 'password_reset')",
            name=op.f("ck_account_tokens_purpose"),
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
            name=op.f("fk_account_tokens_account_id_accounts"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_account_tokens")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_account_tokens_token_hash")),
    )
    op.create_index(
        "ix_account_tokens_account_purpose",
        "account_tokens",
        ["account_id", "purpose", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_account_tokens_account_purpose", table_name="account_tokens")
    op.drop_table("account_tokens")
