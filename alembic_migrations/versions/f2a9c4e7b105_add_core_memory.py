"""Add the core memory table (MEM-001, MEM-011).

Additive only.

Revision ID: f2a9c4e7b105
Revises: e5c1f7a93d20
Create Date: 2026-11-04
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "f2a9c4e7b105"
down_revision = "e5c1f7a93d20"
branch_labels = None
depends_on = None

OWNER_LENGTH = 255


def upgrade() -> None:
    op.create_table(
        "core_memory",
        sa.Column("owner_principal", sa.String(OWNER_LENGTH), primary_key=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("content", postgresql.JSONB(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("core_memory")
