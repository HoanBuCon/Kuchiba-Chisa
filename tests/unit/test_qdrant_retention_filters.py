"""SAFE-02 regression tests for server-side expiry filtering."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.infrastructure.vector.qdrant.qdrant_service import QdrantService


@pytest.mark.asyncio
async def test_guild_memory_query_excludes_expiry_at_current_second(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = AsyncMock()
    client.search.return_value = []
    monkeypatch.setattr(
        "app.infrastructure.vector.qdrant.qdrant_service.time.time",
        lambda: 1_700_000_000,
    )
    service = QdrantService(client=client)

    await service.search_guild_memories(
        collection="guild_memories",
        query_vector=[0.1],
        guild_id="guild_123",
    )

    query_filter = client.search.call_args.kwargs["query_filter"]
    expiry_filter = query_filter.must_not[0]
    assert expiry_filter.key == "expires_at"
    assert expiry_filter.range.lte == 1_700_000_000
