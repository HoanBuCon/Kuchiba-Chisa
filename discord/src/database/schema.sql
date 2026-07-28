CREATE TABLE IF NOT EXISTS discord_users (
    id BIGSERIAL PRIMARY KEY,
    discord_user_id TEXT NOT NULL,
    discord_guild_id TEXT NOT NULL DEFAULT 'DM',
    core_user_id UUID NOT NULL UNIQUE,
    discord_user_name TEXT,
    discord_user_global_name TEXT,
    discord_user_tag TEXT,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_cleared_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Migration: Support server-scoped memory
DO $$
BEGIN
    -- Drop the unique constraint on discord_user_id if it exists
    IF EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'discord_users_discord_user_id_key'
    ) THEN
        ALTER TABLE discord_users DROP CONSTRAINT discord_users_discord_user_id_key;
    END IF;
END $$;

ALTER TABLE discord_users ADD COLUMN IF NOT EXISTS discord_guild_id TEXT NOT NULL DEFAULT 'DM';

CREATE UNIQUE INDEX IF NOT EXISTS idx_discord_users_uid_gid ON discord_users (discord_user_id, discord_guild_id);
CREATE INDEX IF NOT EXISTS idx_discord_users_core_user_id ON discord_users (core_user_id);
CREATE INDEX IF NOT EXISTS idx_discord_users_last_seen_at ON discord_users (last_seen_at DESC);


CREATE TABLE IF NOT EXISTS guild_settings (
    id BIGSERIAL PRIMARY KEY,
    discord_guild_id TEXT NOT NULL,
    chisa_channel_id TEXT NOT NULL,
    setup_by_user_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Migration: Support multiple direct-chat channels per server
DO $$
BEGIN
    -- Drop unique constraint on discord_guild_id if it exists
    IF EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'guild_settings_discord_guild_id_key'
    ) THEN
        ALTER TABLE guild_settings DROP CONSTRAINT guild_settings_discord_guild_id_key;
    END IF;
END $$;

DELETE FROM guild_settings WHERE chisa_channel_id IS NULL;
ALTER TABLE guild_settings ALTER COLUMN chisa_channel_id SET NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_guild_settings_channel_unique ON guild_settings (chisa_channel_id);


CREATE TABLE IF NOT EXISTS discord_interactions (
    id BIGSERIAL PRIMARY KEY,
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
);

CREATE INDEX IF NOT EXISTS idx_discord_interactions_user_id ON discord_interactions (discord_user_id);
CREATE INDEX IF NOT EXISTS idx_discord_interactions_core_user_id ON discord_interactions (core_user_id);
CREATE INDEX IF NOT EXISTS idx_discord_interactions_channel_id ON discord_interactions (discord_channel_id);
CREATE INDEX IF NOT EXISTS idx_discord_interactions_created_at ON discord_interactions (created_at DESC);
