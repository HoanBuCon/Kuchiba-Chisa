"""Focused BE-03 replay, fencing, and compatibility contracts."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.interfaces.llm_provider import LLMResponse
from app.domain.models.background_job import (
    BackgroundJobType,
    BackgroundTurnSource,
    ClaimedBackgroundJob,
)
from app.domain.models.community_state import (
    CommunityMutationResult,
    CommunityStateSnapshot,
)
from app.domain.services.chat_engine import ChatEngine, ChatEngineBusyError
from app.domain.services.chat_pipeline.context import ChatContext
from app.domain.services.community.topic_summarizer import CommunityTopicSummarizer
from app.infrastructure.background.job_handlers import (
    CommunityStateJobHandler,
    PrivateSummaryJobHandler,
)
from app.infrastructure.cache.redis.redis_service import RedisService


def _job(
    job_type: BackgroundJobType,
    payload: dict[str, object],
    *,
    principal_id: uuid.UUID,
    tenant_id: str | None = None,
) -> ClaimedBackgroundJob:
    return ClaimedBackgroundJob(
        job_id=uuid.uuid4(),
        job_type=job_type,
        idempotency_key=f"be03-{uuid.uuid4()}",
        payload=payload,
        payload_version=1,
        principal_id=principal_id,
        tenant_id=tenant_id,
        attempt_count=1,
        max_attempts=3,
        lease_owner="test-worker",
        lease_token=uuid.uuid4(),
        lease_expires_at=datetime.now(UTC) + timedelta(minutes=1),
    )


@pytest.mark.asyncio
async def test_legacy_private_summary_job_uses_safe_current_watermark() -> None:
    user_id = uuid.uuid4()
    source = MagicMock()
    source.ensure_consent = AsyncMock(return_value="external-user")
    callback = AsyncMock()
    handler = PrivateSummaryJobHandler(source, callback)
    conversation_id = uuid.uuid4()

    await handler.handle(
        _job(
            BackgroundJobType.PRIVATE_SUMMARY,
            {
                "user_id": str(user_id),
                "conversation_id": str(conversation_id),
            },
            principal_id=user_id,
        )
    )

    callback.assert_awaited_once_with(
        "external-user",
        str(conversation_id),
        propagate_errors=True,
        source_revision=None,
    )


@pytest.mark.asyncio
async def test_duplicate_community_delivery_does_not_repeat_published_summary() -> None:
    user_id = uuid.uuid4()
    source = MagicMock()
    source.ensure_consent = AsyncMock()
    source.load = AsyncMock(
        return_value=BackgroundTurnSource(
            external_user_id="external-user",
            user_message="hello",
            assistant_message="hi",
            history=[],
            media_metadata=[],
        )
    )
    store = MagicMock()
    store.apply_turn = AsyncMock(
        return_value=CommunityMutationResult(
            applied=False,
            state_revision=30,
            message_count=30,
        )
    )
    store.snapshot = AsyncMock(
        return_value=CommunityStateSnapshot(
            state_revision=30,
            message_count=30,
            messages=[],
            topic_summary="already published",
            topic_summary_revision=30,
        )
    )
    summarizer = MagicMock()
    summarizer.SUMMARIZE_INTERVAL = 30
    summarizer.summarize_channel_topic = AsyncMock()
    handler = CommunityStateJobHandler(source, store, summarizer)
    conversation_id = uuid.uuid4()
    user_message_id = uuid.uuid4()
    assistant_message_id = uuid.uuid4()

    await handler.handle(
        _job(
            BackgroundJobType.COMMUNITY_STATE,
            {
                "user_id": str(user_id),
                "conversation_id": str(conversation_id),
                "user_message_id": str(user_message_id),
                "assistant_message_id": str(assistant_message_id),
                "guild_id": "guild-1",
                "channel_id": "channel-1",
                "speaker_name": "member",
                "ambient_delta": {"joy": 0.01},
                "trace_id": None,
            },
            principal_id=user_id,
            tenant_id="guild-1",
        )
    )

    summarizer.summarize_channel_topic.assert_not_awaited()


@pytest.mark.asyncio
async def test_versioned_summarizer_uses_only_frozen_snapshot() -> None:
    cache = MagicMock()
    cache.get = AsyncMock(side_effect=AssertionError("live summary read is forbidden"))
    cache.get_json = AsyncMock(side_effect=AssertionError("live buffer read is forbidden"))
    llm = MagicMock()
    llm.generate = AsyncMock(
        return_value=LLMResponse(
            raw_content='{"topic_summary":"summary"}',
            parsed={"topic_summary": "summary"},
        )
    )
    store = MagicMock()
    store.publish_summary = AsyncMock(return_value=True)
    summarizer = CommunityTopicSummarizer(llm=llm, cache=cache, state_store=store)

    result = await summarizer.summarize_channel_topic(
        channel_id="channel-1",
        guild_id="guild-1",
        messages=[
            {"speaker_name": "A", "content": "one", "is_bot": False},
            {"speaker_name": "Chisa", "content": "two", "is_bot": True},
        ],
        previous_summary_snapshot="previous",
        source_revision=30,
        propagate_errors=True,
    )

    assert result == "summary"
    cache.get.assert_not_awaited()
    cache.get_json.assert_not_awaited()
    store.publish_summary.assert_awaited_once()


@pytest.mark.asyncio
async def test_redis_outage_fails_lock_acquisition_closed() -> None:
    cache = RedisService()
    cache._client = MagicMock()
    cache._client.set = AsyncMock(side_effect=ConnectionError("redis unavailable"))

    assert await cache.acquire_lock("be03:unavailable", ttl=5) is None


@pytest.mark.asyncio
async def test_stale_chat_lock_owner_cannot_commit() -> None:
    pipeline = MagicMock()
    pipeline.execute = AsyncMock(
        side_effect=lambda context: ChatContext(
            session=context.session,
            user_id=context.user_id,
            user_message=context.user_message,
            chisa_reply="reply",
        )
    )
    cache = MagicMock()
    cache.acquire_lock = AsyncMock(return_value="owner-token")
    cache.renew_lock = AsyncMock(return_value=False)
    cache.release_lock = AsyncMock(return_value=True)
    session = MagicMock()
    session.commit = AsyncMock()
    engine = ChatEngine(
        pipeline=pipeline,
        uow_factory=MagicMock(),
        cache_provider=cache,
        emotion_repo_factory=MagicMock(),
        conv_repo_factory=MagicMock(),
        user_repo_factory=MagicMock(),
        db_session_factory=MagicMock(),
        llm=MagicMock(),
        embedder=MagicMock(),
        vector_store=MagicMock(),
    )

    with pytest.raises(ChatEngineBusyError):
        await engine.community_chat_detailed(
            session=session,
            channel_id="channel-1",
            user_id=str(uuid.uuid4()),
            user_message="hello",
            speaker_name="member",
            channel_name="general",
            guild_id="guild-1",
            guild_name="Guild",
            recent_messages=[],
        )

    session.commit.assert_not_awaited()
    cache.release_lock.assert_awaited_once_with(
        "chisa:chat_lock:" + pipeline.execute.await_args.args[0].user_id,
        token="owner-token",
    )
