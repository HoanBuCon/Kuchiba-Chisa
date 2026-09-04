"""SEC-04 tests for tenant-scoped, retryable community erasure."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.application.usecases.clear_community_memory import ClearCommunityMemoryUseCase


def _use_case(
    *,
    vector_store: SimpleNamespace | None = None,
    cache_provider: SimpleNamespace | None = None,
) -> tuple[ClearCommunityMemoryUseCase, SimpleNamespace]:
    dependencies = SimpleNamespace(
        vector_store=vector_store
        or SimpleNamespace(delete_by_guild=AsyncMock(), delete_by_user=AsyncMock()),
        cache=cache_provider
        or SimpleNamespace(
            delete=AsyncMock(),
            delete_pattern=AsyncMock(),
            get_json=AsyncMock(return_value=[]),
        ),
        erasure_repo=SimpleNamespace(
            create=AsyncMock(return_value=SimpleNamespace(id=uuid.uuid4())),
            finish=AsyncMock(),
        ),
    )
    use_case = ClearCommunityMemoryUseCase(
        vector_store=dependencies.vector_store,
        cache_provider=dependencies.cache,
        erasure_repo_factory=lambda session: dependencies.erasure_repo,
    )
    return use_case, dependencies


@pytest.mark.asyncio
async def test_clear_community_memory_all_scope_uses_only_tenant_keys() -> None:
    cache_provider = SimpleNamespace(
        delete=AsyncMock(),
        delete_pattern=AsyncMock(),
        get_json=AsyncMock(return_value=["channel-a", "channel-b"]),
    )
    use_case, dependencies = _use_case(cache_provider=cache_provider)

    result = await use_case.execute(SimpleNamespace(), guild_id="tenant-a", scope="all")

    assert result["status"] == "completed"
    assert result["stores"]["qdrant"] == "acknowledged"
    assert result["stores"]["redis"] == "acknowledged"
    dependencies.vector_store.delete_by_guild.assert_awaited_once_with(
        "guild_memories", "tenant-a"
    )
    deleted_keys = {call.args[0] for call in cache_provider.delete.await_args_list}
    assert "chisa:guild:tenant-a:ambient_mood" in deleted_keys
    assert "chisa:guild:tenant-a:channel:channel-a:topic_summary" in deleted_keys
    assert not any("tenant-b" in key for key in deleted_keys)
    cache_provider.delete_pattern.assert_not_awaited()
    assert dependencies.erasure_repo.finish.await_args.kwargs["status"] == "COMPLETED"


@pytest.mark.asyncio
async def test_clear_community_memory_failure_returns_retry_without_false_success() -> None:
    vector_store = SimpleNamespace(
        delete_by_guild=AsyncMock(side_effect=RuntimeError("qdrant unavailable")),
        delete_by_user=AsyncMock(),
    )
    use_case, dependencies = _use_case(vector_store=vector_store)

    result = await use_case.execute(SimpleNamespace(), guild_id="tenant-a", scope="all")

    assert result["status"] == "retry_required"
    assert result["stores"]["failed_store"] == "qdrant"
    assert "redis" not in result["stores"]
    dependencies.cache.delete.assert_not_awaited()
    assert dependencies.erasure_repo.finish.await_args.kwargs["status"] == "RETRY_REQUIRED"


@pytest.mark.asyncio
async def test_clear_community_memory_redis_failure_preserves_qdrant_progress() -> None:
    cache_provider = SimpleNamespace(
        delete=AsyncMock(side_effect=RuntimeError("redis unavailable")),
        delete_pattern=AsyncMock(),
        get_json=AsyncMock(return_value=[]),
    )
    use_case, dependencies = _use_case(cache_provider=cache_provider)

    result = await use_case.execute(SimpleNamespace(), guild_id="tenant-a", scope="all")

    assert result["status"] == "retry_required"
    assert result["stores"]["qdrant"] == "acknowledged"
    assert result["stores"]["failed_store"] == "redis"
    assert dependencies.erasure_repo.finish.await_args.kwargs["status"] == "RETRY_REQUIRED"


@pytest.mark.asyncio
async def test_clear_community_memory_self_scope_uses_verified_tenant_channel_and_user() -> None:
    use_case, dependencies = _use_case()

    result = await use_case.execute(
        SimpleNamespace(),
        guild_id="tenant-a",
        scope="self",
        channel_id="channel-a",
        user_id="discord-user-a",
    )

    assert result["status"] == "completed"
    dependencies.vector_store.delete_by_user.assert_awaited_once()
    deleted_keys = {call.args[0] for call in dependencies.cache.delete.await_args_list}
    assert deleted_keys == {
        "chisa:guild:tenant-a:channel:channel-a:topic_summary",
        "chisa:guild:tenant-a:channel:channel-a:rolling_buffer",
        "chisa:guild:tenant-a:channel:channel-a:msg_count",
    }
