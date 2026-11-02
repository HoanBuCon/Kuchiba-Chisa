"""Add the per-corpus-version structured knowledge tables (KNW-004).

Additive only. The legacy entities and aliases tables stay until the legacy code goes (I5).

Revision ID: d7a2c5e8b914
Revises: c4e8a1d7f352
Create Date: 2026-11-02
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "d7a2c5e8b914"
down_revision = "c4e8a1d7f352"
branch_labels = None
depends_on = None

VERSION_LENGTH = 32


def _jsonb() -> postgresql.JSONB:
    return postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    version = sa.Column("corpus_version", sa.String(length=VERSION_LENGTH), nullable=False)
    op.create_table(
        "kb_entities",
        version.copy(),
        sa.Column("page_id", sa.BigInteger(), autoincrement=False, nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=True),
        sa.Column("fields", _jsonb(), nullable=False),
        sa.Column("nation", sa.String(length=256), nullable=True),
        sa.Column("nation_source", sa.String(length=32), nullable=True),
        sa.Column("game_version", sa.String(length=16), nullable=True),
        sa.Column("version_source", sa.String(length=32), nullable=True),
        sa.PrimaryKeyConstraint("corpus_version", "page_id", name=op.f("pk_kb_entities")),
    )
    op.create_table(
        "kb_aliases",
        version.copy(),
        sa.Column("position", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("alias", sa.Text(), nullable=False),
        sa.Column("target", sa.String(length=512), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("confidence", sa.String(length=16), nullable=False),
        sa.Column("evidence", _jsonb(), nullable=False),
        sa.PrimaryKeyConstraint("corpus_version", "position", name=op.f("pk_kb_aliases")),
    )
    op.create_table(
        "kb_glossary",
        version.copy(),
        sa.Column("position", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("term", sa.Text(), nullable=False),
        sa.Column("definition", sa.Text(), nullable=False),
        sa.Column("pages", sa.Integer(), nullable=False),
        sa.Column("variants", _jsonb(), nullable=False),
        sa.PrimaryKeyConstraint("corpus_version", "position", name=op.f("pk_kb_glossary")),
    )
    op.create_table(
        "kb_quests",
        version.copy(),
        sa.Column("page_id", sa.BigInteger(), autoincrement=False, nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("fields", _jsonb(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("steps", _jsonb(), nullable=False),
        sa.Column("narration", _jsonb(), nullable=False),
        sa.Column("speakers", _jsonb(), nullable=False),
        sa.Column("locations", _jsonb(), nullable=False),
        sa.PrimaryKeyConstraint("corpus_version", "page_id", name=op.f("pk_kb_quests")),
    )
    op.create_table(
        "kb_location_edges",
        version.copy(),
        sa.Column("position", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("child", sa.String(length=512), nullable=False),
        sa.Column("parent", sa.String(length=512), nullable=False),
        sa.Column("source", sa.String(length=512), nullable=False),
        sa.PrimaryKeyConstraint("corpus_version", "position", name=op.f("pk_kb_location_edges")),
    )


def downgrade() -> None:
    for table in ("kb_location_edges", "kb_quests", "kb_glossary", "kb_aliases", "kb_entities"):
        op.drop_table(table)
