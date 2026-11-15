"""Add the core memory consolidation state table (MEM-005).

Additive only.

Revision ID: a7d3e9b21c64
Revises: f2a9c4e7b105
Create Date: 2026-11-15
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "a7d3e9b21c64"
down_revision = "f2a9c4e7b105"
branch_labels = None
depends_on = None

OWNER_LENGTH = 255


def upgrade() -> None:
    op.create_table(
        "core_memory_consolidation",
        sa.Column("owner_principal", sa.String(OWNER_LENGTH), primary_key=True),
        sa.Column("consolidated_through", sa.BigInteger(), nullable=False),
        sa.Column("job_owned", postgresql.JSONB(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("core_memory_consolidation")
