"""Add the append-only admin audit log with a hash chain (SEC-ADM-007).

Additive only. A trigger rejects UPDATE, DELETE and TRUNCATE because the application role
owns the table and a REVOKE would not bind it.

Revision ID: d5e2b8f4a173
Revises: c4d7a1e92b58
Create Date: 2026-11-17
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "d5e2b8f4a173"
down_revision = "c4d7a1e92b58"
branch_labels = None
depends_on = None

REJECT_FUNCTION_SQL = """
CREATE FUNCTION admin_audit_events_reject_change() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'admin_audit_events is append-only (SEC-ADM-007)';
END;
$$ LANGUAGE plpgsql
"""
ROW_TRIGGER_SQL = """
CREATE TRIGGER admin_audit_events_append_only
BEFORE UPDATE OR DELETE ON admin_audit_events
FOR EACH ROW EXECUTE FUNCTION admin_audit_events_reject_change()
"""
TRUNCATE_TRIGGER_SQL = """
CREATE TRIGGER admin_audit_events_no_truncate
BEFORE TRUNCATE ON admin_audit_events
FOR EACH STATEMENT EXECUTE FUNCTION admin_audit_events_reject_change()
"""


def upgrade() -> None:
    op.create_table(
        "admin_audit_events",
        sa.Column("seq", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("actor", sa.String(64), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("target", sa.String(128), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("request_id", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("detail", postgresql.JSONB(), nullable=False),
        sa.Column("prev_hash", sa.String(64), nullable=False),
        sa.Column("hash", sa.String(64), nullable=False, unique=True),
    )
    op.create_index("ix_admin_audit_events_created_at", "admin_audit_events", ["created_at"])
    op.execute(REJECT_FUNCTION_SQL)
    op.execute(ROW_TRIGGER_SQL)
    op.execute(TRUNCATE_TRIGGER_SQL)


def downgrade() -> None:
    op.drop_table("admin_audit_events")
    op.execute("DROP FUNCTION admin_audit_events_reject_change()")
