"""Add section metadata required by the lore parent ORM model.

Revision ID: a17c8d4e91f2
Revises: e81f21a479bc
Create Date: 2026-09-01
"""

from alembic import op
import sqlalchemy as sa


revision = "a17c8d4e91f2"
down_revision = "e81f21a479bc"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("lore_parents", sa.Column("section_id", sa.String(), nullable=True))
    op.add_column("lore_parents", sa.Column("heading_path", sa.String(), nullable=True))
    op.add_column("lore_parents", sa.Column("section_depth", sa.Integer(), nullable=True))
    op.create_index(op.f("ix_lore_parents_section_id"), "lore_parents", ["section_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_lore_parents_section_id"), table_name="lore_parents")
    op.drop_column("lore_parents", "section_depth")
    op.drop_column("lore_parents", "heading_path")
    op.drop_column("lore_parents", "section_id")
