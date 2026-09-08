"""Adopt the Discord adapter schema under Alembic ownership.

Revision ID: 7a8c9d0e1f2b
Revises: e5f3a7c9d102
Create Date: 2026-09-08

This migration is deliberately data-preserving.  It creates absent adapter
tables, adds the two columns introduced by the historical Discord bootstrap,
and converts obsolete single-guild uniqueness to the current scoped indexes.
It never deletes rows.  Existing nullable channel records cause an explicit
failure and require an audited operator remediation before retrying.
"""

from alembic import op

revision = "7a8c9d0e1f2b"
down_revision = "e5f3a7c9d102"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create or adopt the known Discord schema without rewriting row data."""
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS discord_users (
            id BIGSERIAL CONSTRAINT discord_users_pkey PRIMARY KEY,
            discord_user_id TEXT NOT NULL,
            discord_guild_id TEXT NOT NULL DEFAULT 'DM',
            core_user_id UUID NOT NULL
                CONSTRAINT discord_users_core_user_id_key UNIQUE,
            discord_user_name TEXT,
            discord_user_global_name TEXT,
            discord_user_tag TEXT,
            first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_cleared_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "ALTER TABLE discord_users "
        "ADD COLUMN IF NOT EXISTS discord_guild_id TEXT NOT NULL DEFAULT 'DM'"
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conrelid = 'discord_users'::regclass
                  AND conname = 'discord_users_discord_user_id_key'
            ) THEN
                ALTER TABLE discord_users
                    DROP CONSTRAINT discord_users_discord_user_id_key;
            END IF;
        END $$
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_discord_users_uid_gid "
        "ON discord_users (discord_user_id, discord_guild_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_discord_users_core_user_id "
        "ON discord_users (core_user_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_discord_users_last_seen_at "
        "ON discord_users (last_seen_at DESC)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS guild_settings (
            id BIGSERIAL CONSTRAINT guild_settings_pkey PRIMARY KEY,
            discord_guild_id TEXT NOT NULL,
            chisa_channel_id TEXT NOT NULL,
            setup_by_user_id TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            mode TEXT NOT NULL DEFAULT 'private'
        )
        """
    )
    op.execute(
        "ALTER TABLE guild_settings "
        "ADD COLUMN IF NOT EXISTS mode TEXT NOT NULL DEFAULT 'private'"
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM guild_settings WHERE chisa_channel_id IS NULL
            ) THEN
                RAISE EXCEPTION
                    'guild_settings has NULL chisa_channel_id rows; '
                    'backup and remediate before migration';
            END IF;
            IF EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conrelid = 'guild_settings'::regclass
                  AND conname = 'guild_settings_discord_guild_id_key'
            ) THEN
                ALTER TABLE guild_settings
                    DROP CONSTRAINT guild_settings_discord_guild_id_key;
            END IF;
        END $$
        """
    )
    op.execute(
        "ALTER TABLE guild_settings ALTER COLUMN chisa_channel_id SET NOT NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_guild_settings_channel_unique "
        "ON guild_settings (chisa_channel_id)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS guild_clear_cutoffs (
            discord_guild_id TEXT CONSTRAINT guild_clear_cutoffs_pkey PRIMARY KEY,
            cleared_at BIGINT NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS discord_interactions (
            id BIGSERIAL CONSTRAINT discord_interactions_pkey PRIMARY KEY,
            discord_user_id TEXT NOT NULL,
            core_user_id UUID NOT NULL,
            discord_user_name TEXT,
            discord_user_global_name TEXT,
            discord_user_tag TEXT,
            discord_guild_id TEXT,
            discord_guild_name TEXT,
            discord_channel_id TEXT,
            discord_channel_name TEXT,
            discord_message_id TEXT,
            command_name TEXT NOT NULL,
            user_message TEXT NOT NULL,
            assistant_message TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            error_message TEXT,
            core_request_at TIMESTAMPTZ,
            core_response_at TIMESTAMPTZ,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_discord_interactions_user_id "
        "ON discord_interactions (discord_user_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_discord_interactions_core_user_id "
        "ON discord_interactions (core_user_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_discord_interactions_channel_id "
        "ON discord_interactions (discord_channel_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_discord_interactions_created_at "
        "ON discord_interactions (created_at DESC)"
    )


def downgrade() -> None:
    """Refuse an automatic destructive downgrade of adopted adapter tables."""
    raise RuntimeError(
        "DB-01 adoption downgrade is intentionally non-automatic: restore the "
        "pre-migration backup or apply an explicitly approved ownership rollback"
    )
