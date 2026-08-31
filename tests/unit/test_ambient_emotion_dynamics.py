import time
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
import pytest

from app.domain.entities.emotion import EmotionState
from app.domain.entities.user import UserStats
from app.domain.services.budget_mode import BudgetMode
from app.domain.services.chat_pipeline.context import ChatContext
from app.domain.services.chat_pipeline.stages.emotion_update_stage import EmotionUpdateStage
from app.domain.services.chat_pipeline.stages.initialization_stage import InitializationStage
from app.domain.services.community.ambient_manager import AmbientMoodManager
from app.domain.services.context_builder import ContextBuilder
from app.domain.services.emotion_engine import EmotionEngine
from app.domain.services.state_manager import StateManager


def test_ambient_mood_manager_exponential_decay():
    now = 1000000.0
    initial_stored = {
        "joy": 0.90,
        "sadness": 0.80,
        "irritation": 0.70,
        "shyness": 0.60,
        "curiosity": 0.90,
        "comfort": 0.10,
        "last_updated_at": now,
    }

    # At t = 0 (immediately), values should equal stored values
    decay_0 = AmbientMoodManager.calculate_decay(initial_stored, current_time=now)
    assert decay_0["sadness"] == 0.80
    assert decay_0["joy"] == 0.90

    # At t = 1800s (1 half-life = 30 minutes), mood should be halfway to Kuudere baseline
    # Sadness baseline is 0.10. Initial was 0.80. Halfway is 0.10 + (0.80 - 0.10) * 0.5 = 0.45
    decay_30min = AmbientMoodManager.calculate_decay(initial_stored, current_time=now + 1800.0)
    assert pytest.approx(decay_30min["sadness"], abs=0.01) == 0.45
    # Comfort baseline is 0.50. Initial was 0.10. Halfway is 0.50 + (0.10 - 0.50) * 0.5 = 0.30
    assert pytest.approx(decay_30min["comfort"], abs=0.01) == 0.30

    # At t = 18000s (~5 hours), mood should have returned 99% to Kuudere baseline
    decay_long = AmbientMoodManager.calculate_decay(initial_stored, current_time=now + 18000.0)
    assert pytest.approx(decay_long["sadness"], abs=0.01) == 0.10
    assert pytest.approx(decay_long["joy"], abs=0.01) == 0.40
    assert pytest.approx(decay_long["comfort"], abs=0.01) == 0.50


def test_ambient_mood_synthesis_preserves_relational_bonds():
    user_uuid = uuid4()
    emotion = EmotionState(
        user_id=user_uuid,
        trust=0.92,
        attachment=0.75,
        joy=0.50,
        sadness=0.0,
        comfort=0.80,
    )

    ambient_mood = {
        "joy": 0.20,
        "sadness": 0.65,
        "irritation": 0.40,
        "shyness": 0.10,
        "curiosity": 0.30,
        "comfort": 0.20,
    }

    AmbientMoodManager.synthesize_ambient_into_emotion(emotion, ambient_mood)

    # Relational bonds MUST remain strictly intact
    assert emotion.trust == 0.92
    assert emotion.attachment == 0.75

    # Transient channels MUST reflect server ambient mood
    assert emotion.sadness == 0.65
    assert emotion.comfort == 0.20
    assert emotion.irritation == 0.40


@pytest.mark.asyncio
async def test_holistic_multi_user_server_emotion_resonance():
    """
    Simulates a multi-user server scenario:
    1. User A (Provocateur) is rude -> Chisa's ambient irritation rises and comfort drops.
    2. User B (Senpai with high trust) enters -> Chisa's state naturally triggers Affectionate Pout (ấm ức với Senpai).
    3. User C (Stranger with low trust) enters -> Chisa remains Guarded / Annoyed.
    4. User D (in isolated 'private' channel) -> Completely immune to server ambient state.
    """
    server_id = "guild_anime_community"
    cache_store = {}

    mock_cache = MagicMock()

    async def mock_get_json(key):
        return cache_store.get(key)

    async def mock_set_json(key, val, ttl=None):
        cache_store[key] = val

    mock_cache.get_json = AsyncMock(side_effect=mock_get_json)
    mock_cache.set_json = AsyncMock(side_effect=mock_set_json)

    engine = EmotionEngine()

    # Step 1: User A (Provocateur) interacts with rude/hostile sentiment
    user_a_uuid = uuid4()
    emotion_a = EmotionState(user_id=user_a_uuid, trust=0.40, attachment=0.05, sadness=0.05, irritation=0.10)
    mock_emotion_repo = MagicMock()
    mock_emotion_repo.update_emotion = AsyncMock()

    update_stage = EmotionUpdateStage(
        emotion_engine=engine,
        emotion_repo_factory=lambda _: mock_emotion_repo,
        cache_provider=mock_cache,
    )

    context_a = ChatContext(
        session=MagicMock(),
        user_id=str(user_a_uuid),
        user_message="Con bot vô dụng biến đi!",
        guild_id=server_id,
        channel_id="chan_general",
        is_community=True,
    )
    context_a.emotion = emotion_a
    context_a.tool_res = {
        "sentiment": {
            "reaction": "guarded_cold",
            "user_stance": "hostile",
            "intensity": 0.9,
            "variance": 0.3,
        }
    }

    await update_stage.process(context_a)

    # Server ambient cache now holds the elevated irritation from User A's interaction
    assert f"chisa:guild:{server_id}:ambient_mood" in cache_store
    server_ambient = cache_store[f"chisa:guild:{server_id}:ambient_mood"]
    assert server_ambient["irritation"] >= 0.40
    assert server_ambient["comfort"] <= 0.30

    # Step 2: User B (Beloved Senpai with high trust) enters the server shortly after
    user_b_uuid = uuid4()
    mock_stats_b = UserStats(user_id=user_b_uuid, interaction_count=20)
    emotion_b = EmotionState(user_id=user_b_uuid, trust=0.85, attachment=0.60, irritation=0.0, comfort=0.70)

    mock_user_repo = MagicMock()
    mock_user_repo.get_or_create_user = AsyncMock()
    mock_user_repo.get_user_stats = AsyncMock(return_value=mock_stats_b)

    mock_emotion_repo_b = MagicMock()
    mock_emotion_repo_b.get_emotion_state = AsyncMock(return_value=emotion_b)

    mock_conv_repo = MagicMock()
    mock_conv_repo.get_or_create_conversation = AsyncMock(return_value=uuid4())
    mock_conv_repo.get_recent_history = AsyncMock(return_value=[])
    mock_conv_repo.get_latest_summary = AsyncMock(return_value=None)

    init_stage = InitializationStage(
        user_repo_factory=lambda _: mock_user_repo,
        emotion_repo_factory=lambda _: mock_emotion_repo_b,
        conv_repo_factory=lambda _: mock_conv_repo,
        cache_provider=mock_cache,
    )

    mock_session = MagicMock()
    mock_session.commit = AsyncMock()

    context_b = ChatContext(
        session=mock_session,
        user_id=str(user_b_uuid),
        user_message="Anh tới rồi đây Chisa ơi.",
        guild_id=server_id,
        channel_id="chan_semi_private",
        is_community=False,  # Semi-private mode sharing server atmosphere
    )

    result_context_b = await init_stage.process(context_b)

    # Senpai B's personal Trust & Attachment are 100% preserved
    assert result_context_b.emotion.trust == 0.85
    assert result_context_b.emotion.attachment == 0.60
    # But Chisa's ambient irritation is reflected from the server atmosphere
    assert result_context_b.emotion.irritation >= 0.40

    # A high-irritation server ambient state cannot be reclassified as an affectionate dyad.
    # The personal relationship remains intact, but the response mood stays guarded/playful.
    dyad_b = StateManager.get_emotional_dyad(result_context_b.emotion)
    assert dyad_b is None
    assert StateManager.get_mood(result_context_b.emotion) == "Playful Pout"

    # Step 3: User C (Stranger with low trust = 0.20) enters
    user_c_uuid = uuid4()
    emotion_c = EmotionState(user_id=user_c_uuid, trust=0.20, attachment=0.0, irritation=0.0, comfort=0.50)
    mock_emotion_repo_c = MagicMock()
    mock_emotion_repo_c.get_emotion_state = AsyncMock(return_value=emotion_c)

    init_stage_c = InitializationStage(
        user_repo_factory=lambda _: mock_user_repo,
        emotion_repo_factory=lambda _: mock_emotion_repo_c,
        conv_repo_factory=lambda _: mock_conv_repo,
        cache_provider=mock_cache,
    )

    context_c = ChatContext(
        session=mock_session,
        user_id=str(user_c_uuid),
        user_message="Ai đây?",
        guild_id=server_id,
        channel_id="chan_general",
        is_community=True,
    )

    result_context_c = await init_stage_c.process(context_c)

    # For Stranger C, Trust is low (0.20) -> StateManager DOES NOT trigger Affectionate Pout (which requires trust >= 0.65)
    dyad_c = StateManager.get_emotional_dyad(result_context_c.emotion)
    assert dyad_c is None  # Does not pout lovingly with strangers
    mood_c = StateManager.get_mood(result_context_c.emotion)
    assert mood_c == "Annoyed"  # Is genuinely annoyed/guarded with stranger

    # Step 4: User D in Isolated Private Channel ('CHANNEL_vip_123')
    user_d_uuid = uuid4()
    emotion_d = EmotionState(user_id=user_d_uuid, trust=0.90, attachment=0.70, irritation=0.05, comfort=0.80)
    mock_emotion_repo_d = MagicMock()
    mock_emotion_repo_d.get_emotion_state = AsyncMock(return_value=emotion_d)

    init_stage_d = InitializationStage(
        user_repo_factory=lambda _: mock_user_repo,
        emotion_repo_factory=lambda _: mock_emotion_repo_d,
        conv_repo_factory=lambda _: mock_conv_repo,
        cache_provider=mock_cache,
    )

    context_d = ChatContext(
        session=mock_session,
        user_id=str(user_d_uuid),
        user_message="Chào em trong phòng VIP nhé.",
        guild_id="CHANNEL_vip_123",  # Isolated channel identifier
        channel_id="vip_123",
        is_community=False,
    )

    result_context_d = await init_stage_d.process(context_d)

    # Completely immune to server ambient irritation
    assert result_context_d.emotion.irritation == 0.05
    assert result_context_d.emotion.comfort == 0.80
