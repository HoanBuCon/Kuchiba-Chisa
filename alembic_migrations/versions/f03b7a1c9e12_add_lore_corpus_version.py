"""Add additive corpus-version provenance to staged lore parents.

Revision ID: f03b7a1c9e12
Revises: d1e4a9f7c204
Create Date: 2026-09-05
"""

from alembic import op
import sqlalchemy as sa


revision = "f03b7a1c9e12"
down_revision = "d1e4a9f7c204"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add nullable provenance without rewriting or deleting active parent records."""
    op.add_column("lore_parents", sa.Column("corpus_version", sa.String(), nullable=True))
    op.create_index(
        op.f("ix_lore_parents_corpus_version"),
        "lore_parents",
        ["corpus_version"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_lore_parents_corpus_version"), table_name="lore_parents")
    op.drop_column("lore_parents", "corpus_version")
