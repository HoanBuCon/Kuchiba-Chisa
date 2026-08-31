from unittest.mock import AsyncMock, call

import pytest

from app.application.usecases.clear_community_memory import ClearCommunityMemoryUseCase


@pytest.mark.asyncio
async def test_clear_community_memory_all_scope():
    vector_store = AsyncMock()
    cache_provider = AsyncMock()
    cache_provider.delete_pattern = AsyncMock(return_value=3)

    use_case = ClearCommunityMemoryUseCase(
        vector_store=vector_store,
        cache_provider=cache_provider,
    )

    result = await use_case.execute(guild_id="123456789", scope="all")

    assert result["guild_id"] == "123456789"
    assert result["scope"] == "all"
    assert result["guild_memories_cleared"] is True
    assert result["ambient_mood_cleared"] is True
    assert result["topic_summaries_cleared"] == 3

    vector_store.delete_by_guild.assert_awaited_once_with("guild_memories", "123456789")
    cache_provider.delete.assert_awaited_once_with("chisa:guild:123456789:ambient_mood")
    cache_provider.delete_pattern.assert_has_awaits(
        [
            call("chisa:channel:*:topic_summary"),
            call("chisa:channel:*:rolling_buffer"),
            call("chisa:channel:*:msg_count"),
        ]
    )


@pytest.mark.asyncio
async def test_clear_community_memory_self_scope():
    vector_store = AsyncMock()
    cache_provider = AsyncMock()

    use_case = ClearCommunityMemoryUseCase(
        vector_store=vector_store,
        cache_provider=cache_provider,
    )

    result = await use_case.execute(
        guild_id="123456789",
        scope="self",
        user_id="user_abc_123"
    )

    assert result["guild_id"] == "123456789"
    assert result["scope"] == "self"
    assert result["user_memories_cleared"] is True

    vector_store.delete_by_user.assert_awaited_once()
