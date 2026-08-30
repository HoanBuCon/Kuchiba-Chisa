"""add media_metadata to messages

Revision ID: e81f21a479bc
Revises: 0f3dabac11ac
Create Date: 2026-08-31 00:43:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'e81f21a479bc'
down_revision = 'f2b15808286f'
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column('messages', sa.Column('media_metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True))

def downgrade() -> None:
    op.drop_column('messages', 'media_metadata')
