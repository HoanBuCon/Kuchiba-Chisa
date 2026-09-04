"""Add persisted dimensions used by the emotion state ORM model.

Revision ID: b28e5c7d02a4
Revises: a17c8d4e91f2
Create Date: 2026-09-01
"""

import sqlalchemy as sa
from alembic import op

revision = "b28e5c7d02a4"
down_revision = "a17c8d4e91f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "emotion_state",
        sa.Column("shyness", sa.Float(), nullable=False, server_default=sa.text("0.0")),
    )
    op.add_column(
        "emotion_state",
        sa.Column("curiosity", sa.Float(), nullable=False, server_default=sa.text("0.10")),
    )
    op.add_column(
        "emotion_state",
        sa.Column("comfort", sa.Float(), nullable=False, server_default=sa.text("0.50")),
    )
    op.alter_column("emotion_state", "shyness", server_default=None)
    op.alter_column("emotion_state", "curiosity", server_default=None)
    op.alter_column("emotion_state", "comfort", server_default=None)


def downgrade() -> None:
    op.drop_column("emotion_state", "comfort")
    op.drop_column("emotion_state", "curiosity")
    op.drop_column("emotion_state", "shyness")
