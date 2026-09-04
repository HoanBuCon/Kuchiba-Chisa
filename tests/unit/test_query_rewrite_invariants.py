from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.interfaces.llm_provider import LLMResponse
from app.domain.models.intent_result import ChatIntent
from app.domain.services.chat_pipeline.context import ChatContext
from app.domain.services.chat_pipeline.stages.intent_stage import (
    IntentStage,
    QueryEmbeddingUnavailableError,
)
from app.domain.services.rag.pipeline import RAGPipeline, VectorQueryInvariantError
from app.domain.services.rag.query_rewriter import QueryRewriter, RewriteResult


def _intent_stage(
    rewrite_result: RewriteResult,
    embedding: list[float],
) -> tuple[IntentStage, MagicMock, MagicMock]:
    classifier = MagicMock()
    classifier.is_small_talk_hybrid = AsyncMock(return_value=(False, "knowledge"))
    classifier.detect_persona_trait = AsyncMock(return_value=None)

    embedder = MagicMock()
    embedder.embed_text = AsyncMock(return_value=embedding)

    rewriter = MagicMock()
    rewriter.rewrite = AsyncMock(return_value=rewrite_result)
    return IntentStage(classifier, embedder, rewriter), embedder, classifier


@pytest.mark.asyncio
async def test_lore_query_embeds_rewritten_query_before_vector_retrieval() -> None:
    rewritten_query = "Kuchiba Chisa Forte Circuit mechanics"
    stage, embedder, classifier = _intent_stage(
        RewriteResult(
            rewritten_query=rewritten_query,
            method="LLM_FLASH",
            needs_vector_search=True,
            needs_web_search=False,
        ),
        [0.1, 0.2],
    )

    result = await stage.process(
        ChatContext(session=None, user_id="principal-1", user_message="How does her Forte work?")
    )

    embedder.embed_text.assert_awaited_once_with(rewritten_query, prefix="query: ")
    assert result.query_vector == [0.1, 0.2]
    assert result.intent_result is not None
    assert result.intent_result.query_vector == [0.1, 0.2]
    assert ChatIntent.LORE in result.intents
    classifier.detect_persona_trait.assert_awaited_once_with(
        "How does her Forte work?", query_vector=[0.1, 0.2]
    )


@pytest.mark.asyncio
async def test_past_image_retrieval_embeds_rewritten_query() -> None:
    rewritten_query = "the beach photo shared with principal"
    stage, embedder, _ = _intent_stage(
        RewriteResult(
            rewritten_query=rewritten_query,
            method="LLM_FLASH",
            needs_vector_search=False,
            needs_web_search=False,
            needs_image_retrieval=True,
        ),
        [0.3, 0.4],
    )

    result = await stage.process(
        ChatContext(session=None, user_id="principal-1", user_message="show me the picture again")
    )

    embedder.embed_text.assert_awaited_once_with(rewritten_query, prefix="query: ")
    assert result.needs_image_retrieval is True
    assert result.needs_vector_search is True
    assert result.query_vector == [0.3, 0.4]
    assert ChatIntent.RETRIEVE_PAST_IMAGE in result.intents


@pytest.mark.asyncio
async def test_web_only_query_does_not_create_vector_embedding() -> None:
    stage, embedder, _ = _intent_stage(
        RewriteResult(
            rewritten_query="latest official game announcement",
            method="LLM_FLASH",
            needs_vector_search=False,
            needs_web_search=True,
        ),
        [0.5, 0.6],
    )

    result = await stage.process(
        ChatContext(
            session=None,
            user_id="principal-1",
            user_message="latest official announcement",
        )
    )

    embedder.embed_text.assert_not_awaited()
    assert result.query_vector is None
    assert result.needs_vector_search is False
    assert result.needs_web_search is True


@pytest.mark.asyncio
async def test_vector_routing_fails_closed_when_embedding_is_empty() -> None:
    stage, _, _ = _intent_stage(
        RewriteResult(
            rewritten_query="Kuchiba Chisa Forte Circuit mechanics",
            method="LLM_FLASH",
            needs_vector_search=True,
            needs_web_search=False,
        ),
        [],
    )

    with pytest.raises(QueryEmbeddingUnavailableError, match="no embedding"):
        await stage.process(
            ChatContext(
                session=None,
                user_id="principal-1",
                user_message="How does her Forte work?",
            )
        )


class _NoCallLLM:
    async def generate(self, prompt: object) -> LLMResponse:
        raise AssertionError("Fast-path rewrite must not call the LLM")


class _FailingLLM:
    async def generate(self, prompt: object) -> LLMResponse:
        raise RuntimeError("provider unavailable")


class _ReturningLLM:
    async def generate(self, prompt: object) -> LLMResponse:
        return LLMResponse(
            raw_content="{}",
            parsed={
                "rewritten_query": "Kuchiba Chisa Forte Circuit mechanics",
                "needs_vector_search": True,
                "needs_web_search": False,
                "needs_image_retrieval": False,
            },
            input_tokens=1,
            output_tokens=1,
            model="test",
        )


@pytest.mark.asyncio
async def test_rewrite_result_contract_covers_empty_fast_fallback_and_llm_paths() -> None:
    empty = await QueryRewriter(_NoCallLLM()).rewrite(
        user_message="",
        cleaned_query="",
    )
    fast = await QueryRewriter(_NoCallLLM()).rewrite(
        user_message="Kuchiba Chisa Forte Circuit",
        cleaned_query="Kuchiba Chisa Forte Circuit",
    )
    fallback = await QueryRewriter(_FailingLLM()).rewrite(
        user_message="Kuchiba Chisa Forte Circuit",
        cleaned_query="Kuchiba Chisa Forte Circuit",
        needs_llm_rewrite=True,
    )
    llm = await QueryRewriter(_ReturningLLM()).rewrite(
        user_message="How does her Forte work?",
        cleaned_query="How does her Forte work",
        needs_llm_rewrite=True,
    )

    assert empty == RewriteResult("", "FAST_PATH", False, False, False)
    assert fast == RewriteResult(
        "Kuchiba Chisa Forte Circuit", "FAST_PATH", True, False, False
    )
    assert fallback == RewriteResult(
        "Kuchiba Chisa Forte Circuit", "FAST_PATH_FALLBACK", True, False, False
    )
    assert llm == RewriteResult(
        rewritten_query="Kuchiba Chisa Forte Circuit mechanics",
        method="LLM_FLASH",
        needs_vector_search=True,
        needs_web_search=False,
        needs_image_retrieval=False,
    )


@pytest.mark.asyncio
async def test_rag_pipeline_rejects_vector_route_without_embedding() -> None:
    memory_retriever = MagicMock()
    lore_retriever = MagicMock()
    assessor = MagicMock()
    thinking_loop = MagicMock()
    tracker = MagicMock()
    pipeline = RAGPipeline(
        memory_retriever=memory_retriever,
        lore_retriever=lore_retriever,
        assessor=assessor,
        thinking_loop_agent=thinking_loop,
        pipeline_tracker=tracker,
    )

    with pytest.raises(VectorQueryInvariantError, match="without a query embedding"):
        await pipeline.retrieve_and_align(
            session=None,
            user_id="principal-1",
            user_message="How does her Forte work?",
            query_vector=None,
            cleaned_query="Kuchiba Chisa Forte Circuit mechanics",
            intents=[ChatIntent.LORE],
            current_emotions={},
            history=[],
            llm=MagicMock(),
            embedder=MagicMock(),
            web_search_tool=None,
            needs_vector_search=True,
        )
