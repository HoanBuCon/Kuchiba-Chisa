"""Add the rolling thread summary table (CONV-002, CONV-003, CONV-004).

Additive only.

Revision ID: a7d3e9b2c418
Revises: f2a9c4e7b105
Create Date: 2026-11-15
"""

import sqlalchemy as sa
from alembic import op

revision = "a7d3e9b2c418"
down_revision = "f2a9c4e7b105"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "thread_summaries",
        sa.Column(
            "thread_id",
            sa.UUID(),
            sa.ForeignKey("threads.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("covered_turn_id", sa.UUID(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("thread_summaries")
