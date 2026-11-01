"""Add the per-page silver check ledger (ING-006) and store page categories (ING-013).

Additive only. The ledger holds one row per cleaned page; categories let a families.yaml change
re-classify every page without asking the wiki again (existing rows start empty and are filled by
the next sync).

Revision ID: 9b3f6d2a8c41
Revises: 7c2e9a4d1b30
Create Date: 2026-11-02
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "9b3f6d2a8c41"
down_revision = "7c2e9a4d1b30"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "wiki_pages",
        sa.Column(
            "categories",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.create_table(
        "wiki_page_silver",
        sa.Column("page_id", sa.BigInteger(), autoincrement=False, nullable=False),
        sa.Column("silver_path", sa.String(length=256), nullable=False),
        sa.Column("output_hash", sa.String(length=64), nullable=False),
        sa.Column("verdict", sa.String(length=24), nullable=False),
        sa.Column("reasons", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("unchanged_runs", sa.Integer(), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lkg_path", sa.String(length=256), nullable=True),
        sa.CheckConstraint(
            "verdict IN ('accept', 'empty_after_clean', 'quarantine', 'hold')",
            name=op.f("ck_wiki_page_silver_verdict"),
        ),
        sa.PrimaryKeyConstraint("page_id", name=op.f("pk_wiki_page_silver")),
    )
    op.create_index(op.f("ix_wiki_page_silver_verdict"), "wiki_page_silver", ["verdict"])


def downgrade() -> None:
    op.drop_index(op.f("ix_wiki_page_silver_verdict"), table_name="wiki_page_silver")
    op.drop_table("wiki_page_silver")
    op.drop_column("wiki_pages", "categories")
