"""BE-03 concurrency evidence against isolated PostgreSQL and Redis."""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest
import redis.asyncio as aioredis
from sqlalchemy import delete, select

from app.config.settings import settings
from app.domain.entities.emotion import EmotionMutation
from app.domain.models.background_job import (
    BackgroundJobSubmission,
    BackgroundJobType,
    ClaimedBackgroundJob,
    UserStateCachePayload,
)
from app.domain.models.community_state import CommunityTurn
from app.infrastructure.background.job_handlers import UserStateCacheJobHandler
from app.infrastructure.cache.redis.community_state_store import RedisCommunityStateStore
from app.infrastructure.cache.redis.redis_service import RedisService
from app.infrastructure.database.engine import AsyncSessionFactory
from app.infrastructure.database.models.background_job import DurableBackgroundJobModel
from app.infrastructure.database.models.conversation import Conversation
from app.infrastructure.database.models.emotion_state import EmotionState
from app.infrastructure.database.models.user import User
from app.infrastructure.database.models.user_stats import UserStats
from app.infrastructure.database.repositories.background_job_queue import (
    PostgresDurableBackgroundJobQueue,
)
from app.infrastructure.database.repositories.conversation_repository import (
    SqlAlchemyConversationRepository,
)
from app.infrastructure.database.repositories.emotion_repository import (
    SqlAlchemyEmotionRepository,
)
from app.infrastructure.database.repositories.user_repository import SqlAlchemyUserRepository


def _turn(event_id: str, *, joy: float = 0.01) -> CommunityTurn:
    return CommunityTurn(
        event_id=event_id,
        user_message={"content": f"user-{event_id}", "is_bot": False},
        assistant_message={"content": f"assistant-{event_id}", "is_bot": True},
        ambient_delta={
            "joy": joy,
            "sadness": 0.0,
            "irritation": 0.0,
            "shyness": 0.0,
            "curiosity": 0.0,
            "comfort": 0.0,
        },
    )


def _new_redis_client() -> aioredis.Redis:
    return aioredis.from_url(settings.REDIS_URL, decode_responses=True)


def _claimed_cache_job(
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
    revision: int,
) -> ClaimedBackgroundJob:
    payload = UserStateCachePayload(
        user_id=user_id,
        conversation_id=conversation_id,
        state_revision=revision,
    )
    return ClaimedBackgroundJob(
        job_id=uuid.uuid4(),
        job_type=BackgroundJobType.USER_STATE_CACHE,
        idempotency_key=f"user-state-cache:{user_id}:{revision}",
        payload=payload.as_json(),
        payload_version=1,
        principal_id=user_id,
        tenant_id=None,
        attempt_count=1,
        max_attempts=3,
        lease_owner="be03-worker",
        lease_token=uuid.uuid4(),
        lease_expires_at=datetime.now(UTC) + timedelta(minutes=1),
    )


@pytest.mark.asyncio
async def test_concurrent_replicas_do_not_lose_or_replay_shared_turns() -> None:
    client = _new_redis_client()
    guild_id = f"be03-guild-{uuid.uuid4()}"
    channel_id = f"channel-{uuid.uuid4()}"
    prefix = RedisCommunityStateStore._prefix(guild_id, channel_id)
    stores = [
        RedisCommunityStateStore(client, ttl_seconds=120, ambient_ttl_seconds=120),
        RedisCommunityStateStore(client, ttl_seconds=120, ambient_ttl_seconds=120),
    ]
    try:
        results = await asyncio.gather(
            *(
                stores[index % 2].apply_turn(
                    guild_id=guild_id,
                    channel_id=channel_id,
                    turn=_turn(f"event-{index}"),
                )
                for index in range(25)
            )
        )
        snapshot = await stores[0].snapshot(guild_id=guild_id, channel_id=channel_id)
        ambient = json.loads(await client.get(f"chisa:guild:{guild_id}:ambient_mood"))

        assert sum(result.applied for result in results) == 25
        assert snapshot.message_count == 25
        assert snapshot.state_revision == 25
        assert len(snapshot.messages) == 50
        assert ambient["state_revision"] == 25
        assert ambient["raw_joy"] == pytest.approx(0.40)

        replay = await stores[1].apply_turn(
            guild_id=guild_id,
            channel_id=channel_id,
            turn=_turn("event-7"),
        )
        assert replay.applied is False
        assert replay.message_count == 25
        assert (await stores[0].snapshot(
            guild_id=guild_id, channel_id=channel_id
        )).message_count == 25
    finally:
        await client.delete(
            f"{prefix}:rolling_buffer",
            f"{prefix}:msg_count",
            f"{prefix}:topic_summary",
            f"{prefix}:topic_summary:revision",
            f"{prefix}:processed_events",
            f"chisa:guild:{guild_id}:ambient_mood",
            f"chisa:guild:{guild_id}:community_channels",
        )
        await client.aclose()


@pytest.mark.asyncio
async def test_unrelated_channels_have_independent_versions_and_shared_atomic_ambient() -> None:
    client = _new_redis_client()
    guild_id = f"be03-guild-{uuid.uuid4()}"
    channel_a = f"a-{uuid.uuid4()}"
    channel_b = f"b-{uuid.uuid4()}"
    store = RedisCommunityStateStore(client, ttl_seconds=120, ambient_ttl_seconds=120)
    try:
        await asyncio.gather(
            *(
                store.apply_turn(
                    guild_id=guild_id,
                    channel_id=channel_a if index % 2 else channel_b,
                    turn=_turn(f"event-{index}", joy=0.005),
                )
                for index in range(20)
            )
        )
        snapshot_a, snapshot_b = await asyncio.gather(
            store.snapshot(guild_id=guild_id, channel_id=channel_a),
            store.snapshot(guild_id=guild_id, channel_id=channel_b),
        )
        ambient = json.loads(await client.get(f"chisa:guild:{guild_id}:ambient_mood"))
        assert snapshot_a.message_count == 10
        assert snapshot_b.message_count == 10
        assert ambient["state_revision"] == 20
        assert ambient["raw_joy"] == pytest.approx(0.25)
    finally:
        await client.delete(
            f"chisa:guild:{guild_id}:ambient_mood",
            f"chisa:guild:{guild_id}:community_channels",
        )
        for channel_id in (channel_a, channel_b):
            prefix = RedisCommunityStateStore._prefix(guild_id, channel_id)
            await client.delete(
                f"{prefix}:rolling_buffer",
                f"{prefix}:msg_count",
                f"{prefix}:topic_summary",
                f"{prefix}:topic_summary:revision",
                f"{prefix}:processed_events",
            )
        await client.aclose()


@pytest.mark.asyncio
async def test_stale_summary_snapshot_is_fenced_after_concurrent_append() -> None:
    client = _new_redis_client()
    guild_id = f"be03-guild-{uuid.uuid4()}"
    channel_id = f"channel-{uuid.uuid4()}"
    prefix = RedisCommunityStateStore._prefix(guild_id, channel_id)
    store = RedisCommunityStateStore(client, ttl_seconds=120, ambient_ttl_seconds=120)
    try:
        await store.apply_turn(
            guild_id=guild_id, channel_id=channel_id, turn=_turn("first")
        )
        stale_snapshot = await store.snapshot(guild_id=guild_id, channel_id=channel_id)
        await store.apply_turn(
            guild_id=guild_id, channel_id=channel_id, turn=_turn("second")
        )

        assert not await store.publish_summary(
            guild_id=guild_id,
            channel_id=channel_id,
            source_revision=stale_snapshot.state_revision,
            summary="stale",
        )
        assert await store.publish_summary(
            guild_id=guild_id,
            channel_id=channel_id,
            source_revision=2,
            summary="current",
        )
        assert not await store.publish_summary(
            guild_id=guild_id,
            channel_id=channel_id,
            source_revision=1,
            summary="older",
        )
        assert await client.get(f"{prefix}:topic_summary") == "current"
    finally:
        await client.delete(
            f"{prefix}:rolling_buffer",
            f"{prefix}:msg_count",
            f"{prefix}:topic_summary",
            f"{prefix}:topic_summary:revision",
            f"{prefix}:processed_events",
            f"chisa:guild:{guild_id}:ambient_mood",
            f"chisa:guild:{guild_id}:community_channels",
        )
        await client.aclose()


@pytest.mark.asyncio
async def test_versioned_cache_rejects_stale_event_and_recovers_after_delete() -> None:
    client = _new_redis_client()
    cache = RedisService()
    cache._client = client
    key = f"be03:cache:{uuid.uuid4()}"
    try:
        assert await cache.set_if_newer(key, "v2", 2, 120)
        assert not await cache.set_if_newer(key, "v1", 1, 120)
        assert await cache.get(key) == "v2"
        await cache.delete(key)
        assert await cache.set_if_newer(key, "recreated", 0, 120)
        assert await cache.get(key) == "recreated"
    finally:
        await cache.delete(key)
        await client.aclose()


@pytest.mark.asyncio
async def test_lock_renewal_and_release_are_owner_fenced() -> None:
    client = _new_redis_client()
    cache = RedisService()
    cache._client = client
    key = f"be03:lock:{uuid.uuid4()}"
    try:
        token = await cache.acquire_lock(key, ttl=10)
        assert token is not None
        assert not await cache.renew_lock(key, "stale-owner", ttl=10)
        assert await cache.renew_lock(key, token, ttl=10)
        assert not await cache.release_lock(key, token="stale-owner")
        assert await cache.release_lock(key, token=token)
        assert not await cache.exists(key)
    finally:
        await cache.delete(key)
        await client.aclose()


@pytest.mark.asyncio
async def test_postgres_atomic_user_and_emotion_updates_do_not_lose_writes(
    isolated_postgres: None,
) -> None:
    del isolated_postgres
    user_id = uuid.uuid4()
    async with AsyncSessionFactory() as session:
        session.add(User(id=user_id, username=f"be03-{user_id}"))
        session.add(
            UserStats(
                user_id=user_id,
                interaction_count=0,
                last_seen=0,
                state_revision=0,
            )
        )
        session.add(EmotionState(user_id=user_id, joy=0.15, updated_at=1_000))
        await session.commit()

    mutation = EmotionMutation(joy=0.01)

    async def apply_one(index: int) -> None:
        async with AsyncSessionFactory() as session:
            await SqlAlchemyUserRepository(session).apply_interaction(
                user_id, last_seen=1_000 + index
            )
            await SqlAlchemyEmotionRepository(session).apply_mutation(
                user_id, mutation, updated_at=1_000 + index
            )
            await session.commit()

    await asyncio.gather(*(apply_one(index) for index in range(20)))

    async with AsyncSessionFactory() as session:
        stats = await session.scalar(select(UserStats).where(UserStats.user_id == user_id))
        emotion = await session.scalar(
            select(EmotionState).where(EmotionState.user_id == user_id)
        )
        assert stats is not None
        assert emotion is not None
        assert stats.interaction_count == 20
        assert stats.state_revision == 20
        assert stats.last_seen == 1_019
        assert float(emotion.joy) == pytest.approx(0.35)
        assert emotion.updated_at == 1_019
        await session.execute(delete(User).where(User.id == user_id))
        await session.commit()


@pytest.mark.asyncio
async def test_postgres_summary_compare_and_set_rejects_stale_source(
    isolated_postgres: None,
) -> None:
    del isolated_postgres
    user_id = uuid.uuid4()
    conversation_id = uuid.uuid4()
    async with AsyncSessionFactory() as session:
        session.add(User(id=user_id, username=f"be03-{user_id}"))
        session.add(Conversation(id=conversation_id, user_id=user_id))
        await session.commit()

    async with AsyncSessionFactory() as session:
        repository = SqlAlchemyConversationRepository(session)
        published = await repository.update_summary_if_newer(
            conversation_id,
            "revision 20",
            source_revision=20,
        )
        stale = await repository.update_summary_if_newer(
            conversation_id,
            "revision 10",
            source_revision=10,
        )
        await session.commit()

        assert published is not None
        assert published.revision == 1
        assert published.source_revision == 20
        assert stale is None

    async with AsyncSessionFactory() as session:
        projection = await SqlAlchemyConversationRepository(
            session
        ).get_summary_projection(conversation_id, user_id)
        assert projection is not None
        assert projection.text == "revision 20"
        assert projection.revision == 1
        assert projection.source_revision == 20
        await session.execute(delete(User).where(User.id == user_id))
        await session.commit()

@pytest.mark.asyncio
async def test_outbox_commit_precedes_durable_cache_visibility(
    isolated_postgres: None,
) -> None:
    del isolated_postgres
    client = _new_redis_client()
    cache = RedisService()
    cache._client = client
    queue = PostgresDurableBackgroundJobQueue(AsyncSessionFactory)
    user_id = uuid.uuid4()
    conversation_id = uuid.uuid4()
    key = f"chisa:user:{user_id}:state"
    submission = BackgroundJobSubmission(
        job_type=BackgroundJobType.USER_STATE_CACHE,
        idempotency_key=f"user-state-cache:{user_id}:1",
        payload=UserStateCachePayload(
            user_id=user_id,
            conversation_id=conversation_id,
            state_revision=1,
        ).as_json(),
        principal_id=user_id,
    )
    try:
        async with AsyncSessionFactory() as session:
            session.add(User(id=user_id, username=f"be03-{user_id}"))
            session.add(
                UserStats(
                    user_id=user_id,
                    interaction_count=1,
                    last_seen=1_001,
                    state_revision=1,
                )
            )
            session.add(EmotionState(user_id=user_id, updated_at=1_001))
            session.add(Conversation(id=conversation_id, user_id=user_id))
            await session.flush()
            await queue.enqueue(session, submission)
            assert await cache.get(key) is None
            await session.commit()

        async with AsyncSessionFactory() as session:
            persisted = await session.scalar(
                select(DurableBackgroundJobModel).where(
                    DurableBackgroundJobModel.idempotency_key
                    == submission.idempotency_key
                )
            )
            assert persisted is not None

        handler = UserStateCacheJobHandler(AsyncSessionFactory, cache)
        await handler.handle(_claimed_cache_job(user_id, conversation_id, 1))
        projected = json.loads(await cache.get(key))
        assert projected["state_revision"] == 1
        assert projected["stats"]["interaction_count"] == 1

        async with AsyncSessionFactory() as session:
            await SqlAlchemyUserRepository(session).apply_interaction(
                user_id, last_seen=1_002
            )
            await session.commit()
        await handler.handle(_claimed_cache_job(user_id, conversation_id, 2))
        await handler.handle(_claimed_cache_job(user_id, conversation_id, 1))
        projected = json.loads(await cache.get(key))
        assert projected["state_revision"] == 2
        assert projected["stats"]["interaction_count"] == 2
    finally:
        await cache.delete(key)
        async with AsyncSessionFactory() as session:
            await session.execute(
                delete(DurableBackgroundJobModel).where(
                    DurableBackgroundJobModel.idempotency_key
                    == submission.idempotency_key
                )
            )
            await session.execute(delete(User).where(User.id == user_id))
            await session.commit()
        await client.aclose()
