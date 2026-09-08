"""BE-01 side effects use deterministic identities across delivery retries."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.interfaces.llm_provider import LLMResponse
from app.domain.services.memory_extractor import MemoryExtractor


@pytest.mark.asyncio
async def test_memory_retry_reuses_deterministic_qdrant_point_id() -> None:
    response = LLMResponse(
        raw_content='{"facts": []}',
        parsed={
            "facts": [
                {
                    "type": "user_fact",
                    "content": "Senpai enjoys deterministic integration tests",
                    "importance_score": 0.9,
                }
            ]
        },
        model="deterministic-test",
    )
    llm = MagicMock()
    llm.generate = AsyncMock(return_value=response)
    embedder = MagicMock()
    embedder.embed_text = AsyncMock(return_value=[0.1, 0.2])
    vector_store = MagicMock()
    vector_store.search_by_user = AsyncMock(return_value=[])
    vector_store.upsert_memory = AsyncMock()
    extractor = MemoryExtractor(llm=llm, embedder=embedder, vector_store=vector_store)

    kwargs = {
        "user_id": "trusted-user",
        "conversation_id": "conversation-1",
        "history": [],
        "current_user_message": "Please remember that I enjoy integration tests.",
        "current_assistant_reply": "Understood.",
        "idempotency_key": "memory-extraction:source-message-1",
        "propagate_errors": True,
    }
    await extractor.extract_and_store_batch(**kwargs)
    await extractor.extract_and_store_batch(**kwargs)

    point_ids = [
        call.kwargs["point_id"] for call in vector_store.upsert_memory.await_args_list
    ]
    assert len(point_ids) == 2
    assert point_ids[0] == point_ids[1]


@pytest.mark.asyncio
async def test_memory_worker_path_propagates_provider_failure() -> None:
    llm = MagicMock()
    llm.generate = AsyncMock(side_effect=TimeoutError("provider unavailable"))
    extractor = MemoryExtractor(
        llm=llm,
        embedder=MagicMock(),
        vector_store=MagicMock(),
    )

    with pytest.raises(TimeoutError):
        await extractor.extract_and_store_batch(
            user_id="trusted-user",
            conversation_id="conversation-1",
            history=[],
            current_user_message="Remember this",
            current_assistant_reply="Okay",
            idempotency_key="memory-extraction:source-message-1",
            propagate_errors=True,
        )
