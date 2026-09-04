"""Add durable, non-content corpus release receipts and audit events.

Revision ID: b6d2f9c4e713
Revises: a4c9e7d2b6f1
Create Date: 2026-09-05
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "b6d2f9c4e713"
down_revision = "a4c9e7d2b6f1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add receipts without mutating any active vector collection or corpus data."""
    op.create_table(
        "corpus_releases",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("logical_collection", sa.String(length=32), nullable=False),
        sa.Column("staging_collection", sa.String(length=192), nullable=False),
        sa.Column("corpus_version", sa.String(length=64), nullable=False),
        sa.Column("parent_count", sa.Integer(), nullable=False),
        sa.Column("vector_count", sa.Integer(), nullable=False),
        sa.Column("parent_manifest_checksum", sa.String(length=64), nullable=False),
        sa.Column("vector_manifest_checksum", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["job_id"], ["pipeline_jobs.id"]),
        sa.ForeignKeyConstraint(["source_id"], ["ingestion_sources.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id"),
        sa.UniqueConstraint("staging_collection"),
    )
    op.create_index(op.f("ix_corpus_releases_job_id"), "corpus_releases", ["job_id"])
    op.create_index(op.f("ix_corpus_releases_source_id"), "corpus_releases", ["source_id"])
    op.create_index(
        op.f("ix_corpus_releases_logical_collection"), "corpus_releases", ["logical_collection"]
    )
    op.create_index(
        op.f("ix_corpus_releases_corpus_version"), "corpus_releases", ["corpus_version"]
    )
    op.create_index(op.f("ix_corpus_releases_status"), "corpus_releases", ["status"])
    op.create_table(
        "corpus_release_audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("release_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_id", sa.String(length=128), nullable=False),
        sa.Column("action", sa.String(length=24), nullable=False),
        sa.Column("old_status", sa.String(length=24), nullable=True),
        sa.Column("new_status", sa.String(length=24), nullable=False),
        sa.Column("old_corpus_version", sa.String(length=64), nullable=True),
        sa.Column("new_corpus_version", sa.String(length=64), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["release_id"], ["corpus_releases.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_corpus_release_audit_events_release_id"),
        "corpus_release_audit_events",
        ["release_id"],
    )
    op.create_index(
        op.f("ix_corpus_release_audit_events_actor_id"),
        "corpus_release_audit_events",
        ["actor_id"],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_corpus_release_audit_events_actor_id"),
        table_name="corpus_release_audit_events",
    )
    op.drop_index(
        op.f("ix_corpus_release_audit_events_release_id"),
        table_name="corpus_release_audit_events",
    )
    op.drop_table("corpus_release_audit_events")
    op.drop_index(op.f("ix_corpus_releases_status"), table_name="corpus_releases")
    op.drop_index(op.f("ix_corpus_releases_corpus_version"), table_name="corpus_releases")
    op.drop_index(op.f("ix_corpus_releases_logical_collection"), table_name="corpus_releases")
    op.drop_index(op.f("ix_corpus_releases_source_id"), table_name="corpus_releases")
    op.drop_index(op.f("ix_corpus_releases_job_id"), table_name="corpus_releases")
    op.drop_table("corpus_releases")
