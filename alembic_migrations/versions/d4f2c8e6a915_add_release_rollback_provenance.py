"""Record the retained physical collection for corpus rollback.

Revision ID: d4f2c8e6a915
Revises: c7e1a9d5b804
Create Date: 2026-09-05
"""

import sqlalchemy as sa
from alembic import op


revision = "d4f2c8e6a915"
down_revision = "c7e1a9d5b804"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Store rollback provenance only; do not mutate aliases or collections."""
    op.add_column(
        "corpus_releases",
        sa.Column("previous_active_collection", sa.String(length=192), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("corpus_releases", "previous_active_collection")
