"""Store the titles redirecting to each wiki page, the top alias source (KNW-004).

Additive only; rows start empty and are filled by the next sync.

Revision ID: c4e8a1d7f352
Revises: 9b3f6d2a8c41
Create Date: 2026-11-02
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "c4e8a1d7f352"
down_revision = "9b3f6d2a8c41"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "wiki_pages",
        sa.Column(
            "redirects",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("wiki_pages", "redirects")
