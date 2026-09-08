"""Alembic-owned tables that have no Python ORM repository.

The Discord adapter accesses these tables through parameterized SQL.  They are
registered in the shared metadata so Alembic can detect schema drift without
making the FastAPI process or the Node adapter schema owners at runtime.
The two legacy emotion tables remain registered until a separately approved
data-retirement migration exists.
"""

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ENUM, JSONB, UUID

from app.infrastructure.database.models.base import Base

legacy_emotional_states = Table(
    "emotional_states",
    Base.metadata,
    Column(
        "user_id",
        UUID(as_uuid=True),
        ForeignKey(
            "users.id",
            name="fk_emotional_states_user_id_users",
            ondelete="CASCADE",
        ),
        primary_key=True,
    ),
    Column("affection_score", Integer, nullable=False),
    Column(
        "mood",
        ENUM(
            "NEUTRAL",
            "HAPPY",
            "SHY",
            "JEALOUS",
            "SAD",
            "EXCITED",
            name="mood_enum",
            create_type=False,
        ),
        nullable=False,
    ),
    Column("trust_level", Integer, nullable=False),
    Column("attachment_level", Integer, nullable=False),
    Column("created_at", DateTime, server_default=text("now()"), nullable=False),
    Column("updated_at", DateTime, server_default=text("now()"), nullable=False),
    schema=None,
)

legacy_affection_logs = Table(
    "affection_logs",
    Base.metadata,
    Column(
        "user_id",
        UUID(as_uuid=True),
        ForeignKey(
            "users.id",
            name="fk_affection_logs_user_id_users",
            ondelete="CASCADE",
        ),
        nullable=False,
    ),
    Column(
        "triggered_by_message_id",
        UUID(as_uuid=True),
        ForeignKey(
            "messages.id",
            name="fk_affection_logs_triggered_by_message_id_messages",
            ondelete="SET NULL",
        ),
        nullable=True,
    ),
    Column("delta", Integer, nullable=False),
    Column("reason", String, nullable=True),
    Column("id", UUID(as_uuid=True), server_default=text("gen_random_uuid()"), primary_key=True),
    Column("created_at", DateTime, server_default=text("now()"), nullable=False),
    Column("updated_at", DateTime, server_default=text("now()"), nullable=False),
)
Index("ix_affection_logs_created_desc", legacy_affection_logs.c.created_at)
Index("ix_affection_logs_user_id", legacy_affection_logs.c.user_id)

discord_users = Table(
    "discord_users",
    Base.metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("discord_user_id", Text, nullable=False),
    Column("discord_guild_id", Text, server_default=text("'DM'::text"), nullable=False),
    Column("core_user_id", UUID(as_uuid=True), nullable=False),
    Column("discord_user_name", Text, nullable=True),
    Column("discord_user_global_name", Text, nullable=True),
    Column("discord_user_tag", Text, nullable=True),
    Column("first_seen_at", DateTime(timezone=True), server_default=text("now()"), nullable=False),
    Column("last_seen_at", DateTime(timezone=True), server_default=text("now()"), nullable=False),
    Column("last_cleared_at", DateTime(timezone=True), nullable=True),
    Column("created_at", DateTime(timezone=True), server_default=text("now()"), nullable=False),
    Column("updated_at", DateTime(timezone=True), server_default=text("now()"), nullable=False),
    UniqueConstraint("core_user_id", name="discord_users_core_user_id_key"),
)
Index(
    "idx_discord_users_uid_gid",
    discord_users.c.discord_user_id,
    discord_users.c.discord_guild_id,
    unique=True,
)
Index("idx_discord_users_core_user_id", discord_users.c.core_user_id)
Index("idx_discord_users_last_seen_at", discord_users.c.last_seen_at.desc())

guild_settings = Table(
    "guild_settings",
    Base.metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("discord_guild_id", Text, nullable=False),
    Column("chisa_channel_id", Text, nullable=False),
    Column("setup_by_user_id", Text, nullable=True),
    Column("created_at", DateTime(timezone=True), server_default=text("now()"), nullable=False),
    Column("updated_at", DateTime(timezone=True), server_default=text("now()"), nullable=False),
    Column("mode", Text, server_default=text("'private'::text"), nullable=False),
)
Index("idx_guild_settings_channel_unique", guild_settings.c.chisa_channel_id, unique=True)

guild_clear_cutoffs = Table(
    "guild_clear_cutoffs",
    Base.metadata,
    Column("discord_guild_id", Text, primary_key=True),
    Column("cleared_at", BigInteger, nullable=False),
    Column("updated_at", DateTime(timezone=True), server_default=text("now()"), nullable=False),
)

discord_interactions = Table(
    "discord_interactions",
    Base.metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("discord_user_id", Text, nullable=False),
    Column("core_user_id", UUID(as_uuid=True), nullable=False),
    Column("discord_user_name", Text, nullable=True),
    Column("discord_user_global_name", Text, nullable=True),
    Column("discord_user_tag", Text, nullable=True),
    Column("discord_guild_id", Text, nullable=True),
    Column("discord_guild_name", Text, nullable=True),
    Column("discord_channel_id", Text, nullable=True),
    Column("discord_channel_name", Text, nullable=True),
    Column("discord_message_id", Text, nullable=True),
    Column("command_name", Text, nullable=False),
    Column("user_message", Text, nullable=False),
    Column("assistant_message", Text, nullable=True),
    Column("status", Text, server_default=text("'pending'::text"), nullable=False),
    Column("error_message", Text, nullable=True),
    Column("core_request_at", DateTime(timezone=True), nullable=True),
    Column("core_response_at", DateTime(timezone=True), nullable=True),
    Column("metadata", JSONB, server_default=text("'{}'::jsonb"), nullable=False),
    Column("created_at", DateTime(timezone=True), server_default=text("now()"), nullable=False),
    Column("updated_at", DateTime(timezone=True), server_default=text("now()"), nullable=False),
)
Index("idx_discord_interactions_user_id", discord_interactions.c.discord_user_id)
Index("idx_discord_interactions_core_user_id", discord_interactions.c.core_user_id)
Index("idx_discord_interactions_channel_id", discord_interactions.c.discord_channel_id)
Index("idx_discord_interactions_created_at", discord_interactions.c.created_at.desc())

