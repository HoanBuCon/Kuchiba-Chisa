"""Add governed ingestion-source registry and parent source provenance.

Revision ID: a4c9e7d2b6f1
Revises: f03b7a1c9e12
Create Date: 2026-09-05
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "a4c9e7d2b6f1"
down_revision = "f03b7a1c9e12"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add source governance without deleting or rewriting active corpus records."""
    op.create_table(
        "ingestion_sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("uri", sa.String(length=2048), nullable=False),
        sa.Column("owner_id", sa.String(length=128), nullable=False),
        sa.Column("license_identifier", sa.String(length=128), nullable=False),
        sa.Column("access_scope", sa.String(length=16), nullable=False),
        sa.Column("subject_id", sa.String(length=128), nullable=True),
        sa.Column("tenant_id", sa.String(length=128), nullable=True),
        sa.Column("channel_id", sa.String(length=128), nullable=True),
        sa.Column("trust_tier", sa.String(length=16), nullable=False),
        sa.Column("checksum", sa.String(length=64), nullable=False),
        sa.Column("crawl_schedule", sa.String(length=256), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("approved_by", sa.String(length=128), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_ingestion_sources_owner_id"), "ingestion_sources", ["owner_id"])
    op.create_index(op.f("ix_ingestion_sources_status"), "ingestion_sources", ["status"])
    op.create_index(op.f("ix_ingestion_sources_tenant_id"), "ingestion_sources", ["tenant_id"])
    op.create_table(
        "ingestion_source_audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_id", sa.String(length=128), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("old_status", sa.String(length=16), nullable=True),
        sa.Column("new_status", sa.String(length=16), nullable=False),
        sa.Column("old_checksum", sa.String(length=64), nullable=True),
        sa.Column("new_checksum", sa.String(length=64), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["source_id"], ["ingestion_sources.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_ingestion_source_audit_events_actor_id"),
        "ingestion_source_audit_events",
        ["actor_id"],
    )
    op.create_index(
        op.f("ix_ingestion_source_audit_events_source_id"),
        "ingestion_source_audit_events",
        ["source_id"],
    )
    op.add_column("lore_parents", sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column(
        "lore_parents",
        sa.Column("access_scope", sa.String(length=16), nullable=False, server_default="public"),
    )
    op.add_column("lore_parents", sa.Column("access_subject_id", sa.String(length=128), nullable=True))
    op.add_column("lore_parents", sa.Column("access_tenant_id", sa.String(length=128), nullable=True))
    op.add_column("lore_parents", sa.Column("access_channel_id", sa.String(length=128), nullable=True))
    op.create_index(op.f("ix_lore_parents_access_scope"), "lore_parents", ["access_scope"])
    op.create_index(
        op.f("ix_lore_parents_access_subject_id"), "lore_parents", ["access_subject_id"]
    )
    op.create_index(
        op.f("ix_lore_parents_access_tenant_id"), "lore_parents", ["access_tenant_id"]
    )
    op.create_index(
        op.f("ix_lore_parents_access_channel_id"), "lore_parents", ["access_channel_id"]
    )
    op.create_index(op.f("ix_lore_parents_source_id"), "lore_parents", ["source_id"])
    op.create_foreign_key(
        op.f("fk_lore_parents_source_id_ingestion_sources"),
        "lore_parents",
        "ingestion_sources",
        ["source_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_ingestion_source_audit_events_source_id"),
        table_name="ingestion_source_audit_events",
    )
    op.drop_index(
        op.f("ix_ingestion_source_audit_events_actor_id"),
        table_name="ingestion_source_audit_events",
    )
    op.drop_table("ingestion_source_audit_events")
    op.drop_constraint(
        op.f("fk_lore_parents_source_id_ingestion_sources"),
        "lore_parents",
        type_="foreignkey",
    )
    op.drop_index(op.f("ix_lore_parents_access_channel_id"), table_name="lore_parents")
    op.drop_index(op.f("ix_lore_parents_access_tenant_id"), table_name="lore_parents")
    op.drop_index(op.f("ix_lore_parents_access_subject_id"), table_name="lore_parents")
    op.drop_index(op.f("ix_lore_parents_access_scope"), table_name="lore_parents")
    op.drop_column("lore_parents", "access_channel_id")
    op.drop_column("lore_parents", "access_tenant_id")
    op.drop_column("lore_parents", "access_subject_id")
    op.drop_column("lore_parents", "access_scope")
    op.drop_index(op.f("ix_lore_parents_source_id"), table_name="lore_parents")
    op.drop_column("lore_parents", "source_id")
    op.drop_index(op.f("ix_ingestion_sources_tenant_id"), table_name="ingestion_sources")
    op.drop_index(op.f("ix_ingestion_sources_status"), table_name="ingestion_sources")
    op.drop_index(op.f("ix_ingestion_sources_owner_id"), table_name="ingestion_sources")
    op.drop_table("ingestion_sources")
