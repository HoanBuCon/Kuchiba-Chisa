"""Persist trusted corpus release quality receipts.

Revision ID: c7e1a9d5b804
Revises: b6d2f9c4e713
Create Date: 2026-09-05
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "c7e1a9d5b804"
down_revision = "b6d2f9c4e713"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add aggregate evaluation receipts; no raw prompt, answer, or corpus text is stored."""
    op.create_table(
        "corpus_release_quality_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("release_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("evaluator_version", sa.String(length=128), nullable=False),
        sa.Column("dataset_version", sa.String(length=128), nullable=False),
        sa.Column("sample_size", sa.Integer(), nullable=False),
        sa.Column("confidence_interval", sa.Float(), nullable=False),
        sa.Column("faithfulness", sa.Float(), nullable=False),
        sa.Column("answer_relevance", sa.Float(), nullable=False),
        sa.Column("context_recall", sa.Float(), nullable=False),
        sa.Column("context_precision", sa.Float(), nullable=False),
        sa.Column("citation_correctness", sa.Float(), nullable=False),
        sa.Column("retrieval_hit_at_5", sa.Float(), nullable=False),
        sa.Column("retrieval_mrr_at_10", sa.Float(), nullable=False),
        sa.Column("critical_unsupported_claims", sa.Integer(), nullable=False),
        sa.Column("cross_tenant_leakage_count", sa.Integer(), nullable=False),
        sa.Column("prompt_leakage_count", sa.Integer(), nullable=False),
        sa.Column("human_audit_completed", sa.Boolean(), nullable=False),
        sa.Column("security_slice_passed", sa.Boolean(), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["release_id"], ["corpus_releases.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("release_id"),
    )
    op.create_index(
        op.f("ix_corpus_release_quality_reports_release_id"),
        "corpus_release_quality_reports",
        ["release_id"],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_corpus_release_quality_reports_release_id"),
        table_name="corpus_release_quality_reports",
    )
    op.drop_table("corpus_release_quality_reports")
