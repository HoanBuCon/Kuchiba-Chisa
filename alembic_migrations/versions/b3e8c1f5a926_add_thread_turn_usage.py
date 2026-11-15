"""Add token usage and estimated cost to thread turns (COST-001, MODE-006).

Additive only: nullable, so turns stored before this revision stay valid.

Revision ID: b3e8c1f5a926
Revises: a7d3e9b2c418
Create Date: 2026-11-15
"""

import sqlalchemy as sa
from alembic import op

revision = "b3e8c1f5a926"
down_revision = "a7d3e9b2c418"
branch_labels = None
depends_on = None

USAGE_COLUMNS = (
    ("input_tokens", sa.Integer),
    ("cached_input_tokens", sa.Integer),
    ("output_tokens", sa.Integer),
    ("cost_usd", sa.Float),
)


def upgrade() -> None:
    for name, column_type in USAGE_COLUMNS:
        op.add_column("thread_turns", sa.Column(name, column_type(), nullable=True))


def downgrade() -> None:
    for name, _ in reversed(USAGE_COLUMNS):
        op.drop_column("thread_turns", name)
