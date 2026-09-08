"""Add monotonic revisions for cache and summary fencing.

Revision ID: 9c0e1f2a3b4d
Revises: 8b9d0e1f2a3c
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "9c0e1f2a3b4d"
down_revision: str | None = "8b9d0e1f2a3c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "user_stats",
        sa.Column("state_revision", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "conversations",
        sa.Column("summary_revision", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "conversations",
        sa.Column("summary_source_revision", sa.Integer(), server_default="0", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("conversations", "summary_source_revision")
    op.drop_column("conversations", "summary_revision")
    op.drop_column("user_stats", "state_revision")
