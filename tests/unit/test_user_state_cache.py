"""
Unit tests for Redis Write-Through User State Cache (UserStateCache).
"""
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.domain.entities.user import UserStats as UserStatsEntity
from app.domain.entities.emotion import EmotionState as EmotionStateEntity
from app.domain.services.user_state_cache import UserStateCache
from app.domain.services.chat_pipeline.context import ChatContext
from app.domain.services.chat_pipeline.stages.initialization_stage import InitializationStage
from app.domain.services.chat_pipeline.stages.persistence_stage import PersistenceStage


class InMemoryMockCache:
    def __init__(self):
        self.store = {}
        self.revisions = {}

    async def get_json(self, key: str):
        return self.store.get(key)

    async def set_json(self, key: str, value: dict, ttl: int = None):
        self.store[key] = value

    async def set_if_newer(self, key: str, value: str, revision: int, ttl: int) -> bool:
        del ttl
        if revision <= self.revisions.get(key, -1):
            return False
        import json

        self.store[key] = json.loads(value)
        self.revisions[key] = revision
        return True

    async def delete(self, key: str):
        self.store.pop(key, None)


@pytest.mark.asyncio
async def test_user_state_cache_set_and_get():
    cache = InMemoryMockCache()
    user_id = uuid.uuid4()
    conv_id = uuid.uuid4()

    stats = UserStatsEntity(user_id=user_id, interaction_count=15, last_seen=1700000000000)
    emotion = EmotionStateEntity(
        user_id=user_id,
        joy=0.45,
        sadness=0.05,
        trust=0.75,
        attachment=0.30,
        irritation=0.02,
        shyness=0.12,
        curiosity=0.22,
        comfort=0.62,
        updated_at=1700000000000,
    )

    # 1. Set state
    await UserStateCache.set_state(cache, user_id, stats, emotion, conv_id)

    # 2. Get state
    result = await UserStateCache.get_state(cache, user_id)
    assert result is not None
    cached_stats, cached_emotion, cached_conv_id = result

    assert cached_stats.user_id == user_id
    assert cached_stats.interaction_count == 15
    assert cached_stats.last_seen == 1700000000000

    assert cached_emotion.user_id == user_id
    assert cached_emotion.joy == 0.45
    assert cached_emotion.trust == 0.75
    assert cached_emotion.attachment == 0.30
    assert cached_conv_id == conv_id

    # 3. Invalidate
    await UserStateCache.invalidate(cache, user_id)
    result_after_invalidate = await UserStateCache.get_state(cache, user_id)
    assert result_after_invalidate is None


@pytest.mark.asyncio
async def test_initialization_stage_uses_canonical_database_state():
    cache = InMemoryMockCache()
    user_id = "test_user_cache_123"
    from app.shared.utils.user_identity import normalize_user_id
    user_uuid = normalize_user_id(user_id)
    conv_id = uuid.uuid4()

    # Pre-populate cache
    stats = UserStatsEntity(
        user_id=user_uuid,
        interaction_count=42,
        last_seen=1700000000000,
        state_revision=42,
    )
    emotion = EmotionStateEntity(user_id=user_uuid, joy=0.8, trust=0.9, updated_at=1700000000000)
    await UserStateCache.set_state(cache, user_uuid, stats, emotion, conv_id)

    # Mock Repos
    user_repo = MagicMock()
    user_repo.get_or_create_user = AsyncMock()
    canonical_stats = UserStatsEntity(
        user_id=user_uuid,
        interaction_count=43,
        last_seen=1700000000001,
        state_revision=43,
    )
    user_repo.get_user_stats = AsyncMock(return_value=canonical_stats)

    emotion_repo = MagicMock()
    canonical_emotion = EmotionStateEntity(
        user_id=user_uuid, joy=0.7, trust=0.85, updated_at=1700000000001
    )
    emotion_repo.get_emotion_state = AsyncMock(return_value=canonical_emotion)

    conv_repo = MagicMock()
    conv_repo.get_or_create_conversation = AsyncMock(return_value=conv_id)
    conv_repo.get_recent_history = AsyncMock(return_value=[])
    conv_repo.get_latest_summary = AsyncMock(return_value=None)

    stage = InitializationStage(
        user_repo_factory=lambda session: user_repo,
        emotion_repo_factory=lambda session: emotion_repo,
        conv_repo_factory=lambda session: conv_repo,
        cache_provider=cache,
    )

    ctx = ChatContext(user_id=user_id, user_message="hello", session=MagicMock())
    ctx.session.commit = AsyncMock()

    res = await stage.process(ctx)

    # Mutable request state is read from the transactionally canonical database.
    assert res.stats.interaction_count == 43
    assert res.emotion.joy == 0.7
    assert res.conv_id == conv_id
    user_repo.get_user_stats.assert_awaited_once_with(user_uuid)
    emotion_repo.get_emotion_state.assert_awaited_once_with(user_uuid)


@pytest.mark.asyncio
async def test_persistence_stage_uses_atomic_canonical_interaction_update():
    cache = InMemoryMockCache()
    user_id = "test_persist_user"
    from app.shared.utils.user_identity import normalize_user_id
    user_uuid = normalize_user_id(user_id)
    conv_id = uuid.uuid4()

    user_repo = MagicMock()
    updated_stats = UserStatsEntity(
        user_id=user_uuid,
        interaction_count=6,
        last_seen=200,
        state_revision=6,
    )
    user_repo.apply_interaction = AsyncMock(return_value=updated_stats)
    conv_repo = MagicMock()
    conv_repo.save_message = AsyncMock()

    stage = PersistenceStage(
        user_repo_factory=lambda session: user_repo,
        conv_repo_factory=lambda session: conv_repo,
        cache_provider=cache,
    )

    stats = UserStatsEntity(user_id=user_uuid, interaction_count=5, last_seen=100)
    emotion = EmotionStateEntity(user_id=user_uuid, joy=0.6, trust=0.7, updated_at=100)

    ctx = ChatContext(
        user_id=user_id,
        user_uuid=user_uuid,
        conv_id=conv_id,
        user_message="ping",
        chisa_reply="pong",
        stats=stats,
        emotion=emotion,
        session=MagicMock(),
    )

    await stage.process(ctx)

    user_repo.apply_interaction.assert_awaited_once()
    assert ctx.stats is updated_stats
    assert ctx.state_revision == 6
    assert await UserStateCache.get_state(cache, user_uuid) is None
