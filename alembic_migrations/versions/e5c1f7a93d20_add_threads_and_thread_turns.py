"""Add v2 threads and their turns (CONV-001, MODE-006, GRD-005).

Additive only. Legacy conversations and messages stay until the old chat path is removed in R6.

Revision ID: e5c1f7a93d20
Revises: d7a2c5e8b914
Create Date: 2026-11-04
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "e5c1f7a93d20"
down_revision = "d7a2c5e8b914"
branch_labels = None
depends_on = None

OWNER_LENGTH = 255
LABEL_LENGTH = 32


def upgrade() -> None:
    op.create_table(
        "threads",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("owner_principal", sa.String(OWNER_LENGTH), nullable=False),
        sa.Column("channel", sa.String(LABEL_LENGTH), nullable=False),
        sa.Column("mode", sa.String(LABEL_LENGTH), nullable=False),
        sa.Column("title", sa.String(OWNER_LENGTH), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_threads_owner_created", "threads", ["owner_principal", "created_at"])
    op.create_table(
        "thread_turns",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "thread_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("threads.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("turn_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("mode_requested", sa.String(LABEL_LENGTH), nullable=False),
        sa.Column("mode_effective", sa.String(LABEL_LENGTH), nullable=False),
        sa.Column("lane", sa.String(LABEL_LENGTH), nullable=False),
        sa.Column("status", sa.String(LABEL_LENGTH), nullable=False),
        sa.Column("downgrade_reason", sa.String(LABEL_LENGTH), nullable=True),
        sa.Column("llm_calls", sa.Integer(), nullable=False),
        sa.Column("citations", postgresql.JSONB(), nullable=False),
        sa.Column("degraded", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("thread_id", "turn_id", name="uq_thread_turns_turn"),
    )
    op.create_index("ix_thread_turns_thread_created", "thread_turns", ["thread_id", "created_at"])


def downgrade() -> None:
    op.drop_table("thread_turns")
    op.drop_table("threads")
