"""Add the wiki page inventory and sync-run log for the v2 ingestion (ING-013, ADR-0002).

Additive only; the legacy ``wiki_sync_state`` table is dropped with the legacy pipeline in I5.

Revision ID: 7c2e9a4d1b30
Revises: 4d8e2b6c1f37
Create Date: 2026-11-01
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "7c2e9a4d1b30"
down_revision = "4d8e2b6c1f37"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "wiki_pages",
        sa.Column("page_id", sa.BigInteger(), autoincrement=False, nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("last_revid", sa.BigInteger(), nullable=False),
        sa.Column("touched", sa.DateTime(timezone=True), nullable=False),
        sa.Column("family", sa.String(length=64), nullable=True),
        sa.Column("tier", sa.String(length=8), nullable=True),
        sa.Column("templates", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("fetched_revid", sa.BigInteger(), nullable=True),
        sa.Column("fetched_touched", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("bronze_key", sa.String(length=256), nullable=True),
        sa.Column("aliases", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.CheckConstraint(
            "status IN ('active', 'pending_delete', 'deleted')",
            name=op.f("ck_wiki_pages_status"),
        ),
        sa.PrimaryKeyConstraint("page_id", name=op.f("pk_wiki_pages")),
    )
    op.create_index(op.f("ix_wiki_pages_title"), "wiki_pages", ["title"])
    op.create_index(op.f("ix_wiki_pages_family"), "wiki_pages", ["family"])
    op.create_index(op.f("ix_wiki_pages_status"), "wiki_pages", ["status"])
    op.create_table(
        "wiki_sync_runs",
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("stats", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.PrimaryKeyConstraint("run_id", name=op.f("pk_wiki_sync_runs")),
    )
    op.create_index(op.f("ix_wiki_sync_runs_started_at"), "wiki_sync_runs", ["started_at"])


def downgrade() -> None:
    op.drop_index(op.f("ix_wiki_sync_runs_started_at"), table_name="wiki_sync_runs")
    op.drop_table("wiki_sync_runs")
    op.drop_index(op.f("ix_wiki_pages_status"), table_name="wiki_pages")
    op.drop_index(op.f("ix_wiki_pages_family"), table_name="wiki_pages")
    op.drop_index(op.f("ix_wiki_pages_title"), table_name="wiki_pages")
    op.drop_table("wiki_pages")
