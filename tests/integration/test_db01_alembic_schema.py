"""DB-01 isolated PostgreSQL checks for Alembic schema ownership."""

from __future__ import annotations

import pytest
from sqlalchemy import text

from app.infrastructure.database.engine import AsyncSessionFactory, check_database_health
from app.infrastructure.database.schema_revision import expected_schema_heads


async def _schema_fingerprint() -> tuple[tuple[object, ...], ...]:
    query = text(
        """
        SELECT c.relkind, c.relname, COALESCE(i.relname, '') AS index_name
        FROM pg_class AS c
        JOIN pg_namespace AS n ON n.oid = c.relnamespace
        LEFT JOIN pg_index AS ix ON ix.indrelid = c.oid
        LEFT JOIN pg_class AS i ON i.oid = ix.indexrelid
        WHERE n.nspname = 'public'
          AND c.relkind IN ('r', 'p')
        ORDER BY c.relkind, c.relname, index_name
        """
    )
    async with AsyncSessionFactory() as session:
        return tuple(tuple(row) for row in (await session.execute(query)).all())


@pytest.mark.asyncio
async def test_alembic_head_contains_discord_schema(isolated_postgres: None) -> None:
    del isolated_postgres
    async with AsyncSessionFactory() as session:
        revision_rows = await session.execute(text("SELECT version_num FROM alembic_version"))
        revisions = frozenset(str(row[0]) for row in revision_rows.all())
        tables = {
            str(row[0])
            for row in (
                await session.execute(
                    text(
                        """
                        SELECT table_name FROM information_schema.tables
                        WHERE table_schema = 'public'
                        """
                    )
                )
            ).all()
        }
        indexes = {
            str(row[0])
            for row in (
                await session.execute(
                    text(
                        """
                        SELECT indexname FROM pg_indexes
                        WHERE schemaname = 'public'
                        """
                    )
                )
            ).all()
        }

    assert revisions == expected_schema_heads()
    assert {
        "discord_users",
        "guild_settings",
        "guild_clear_cutoffs",
        "discord_interactions",
    } <= tables
    assert {
        "idx_discord_users_uid_gid",
        "idx_guild_settings_channel_unique",
        "idx_discord_interactions_created_at",
    } <= indexes


@pytest.mark.asyncio
async def test_runtime_health_check_does_not_mutate_schema(
    isolated_postgres: None,
) -> None:
    del isolated_postgres
    before = await _schema_fingerprint()

    assert await check_database_health() is True

    after = await _schema_fingerprint()
    assert after == before
