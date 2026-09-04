"""Add the persisted rewritten query field used by message history.

Revision ID: c39f6e8a14b5
Revises: b28e5c7d02a4
Create Date: 2026-09-01
"""

import sqlalchemy as sa
from alembic import op

revision = "c39f6e8a14b5"
down_revision = "b28e5c7d02a4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("messages", sa.Column("rewritten_content", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("messages", "rewritten_content")
