from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
import pytest

from app.domain.entities.community import CommunityMessage
from app.domain.entities.emotion import EmotionState
from app.domain.entities.user import UserStats
from app.domain.interfaces.llm_provider import BaseLLMAdapter, LLMResponse
from app.domain.services.budget_mode import BudgetMode
from app.domain.services.chat_engine import ChatEngine, ChatPipeline
from app.domain.services.chat_pipeline.context import ChatContext
from app.domain.services.chat_pipeline.stages.context_building_stage import ContextBuildingStage
from app.domain.services.chat_pipeline.stages.emotion_update_stage import EmotionUpdateStage
from app.domain.services.chat_pipeline.stages.initialization_stage import InitializationStage
from app.domain.services.chat_pipeline.stages.llm_generation_stage import LLMGenerationStage
from app.domain.services.chat_pipeline.stages.persistence_stage import PersistenceStage
from app.domain.services.community.transcript_formatter import ChannelTranscriptFormatter
from app.domain.services.context_builder import ContextBuilder
from app.domain.services.emotion_engine import EmotionEngine


def test_channel_transcript_formatter():
    now = datetime(2026, 8, 30, 1, 15, 0)
    messages = [
        CommunityMessage(
            message_id="msg_1",
            speaker_id="user_1",
            speaker_name="Hoan",
            content="Mọi người ơi tối nay ăn gì nhỉ?",
            created_at=now,
        ),
        CommunityMessage(
            message_id="msg_2",
            speaker_id="user_2",
            speaker_name="Alex",
            content="Ramen đi bác ơi!",
            created_at=now + timedelta(minutes=1),
            reply_to_speaker="Hoan",
        ),
        CommunityMessage(
            message_id="msg_3",
            speaker_id="bot_1",
            speaker_name="Chisa",
            content="Dạ em vote quán ramen miso cay ở ngã tư nhé ~",
            created_at=now + timedelta(minutes=2),
            is_bot=True,
        ),
    ]

    formatted = ChannelTranscriptFormatter.format_transcript(messages, max_tokens=1000)

    assert "[01:15] <Hoan>: Mọi người ơi tối nay ăn gì nhỉ?" in formatted
    assert "[01:16] <Alex> [Replying to @Hoan]: Ramen đi bác ơi!" in formatted
    assert "[01:17] <Chisa>: Dạ em vote quán ramen miso cay ở ngã tư nhé ~" in formatted


def test_channel_transcript_formatter_token_truncation():
    now = datetime.now()
    # Generate 50 long messages
    long_messages = [
        CommunityMessage(
            message_id=f"msg_{i}",
            speaker_id=f"user_{i % 3}",
            speaker_name=f"User_{i % 3}",
            content=f"Đây là tin nhắn thứ {i} chứa rất nhiều nội dung chi tiết thảo luận về thuật toán RAG và kiến trúc cơ sở dữ liệu phân tán.",
            created_at=now + timedelta(minutes=i),
        )
        for i in range(50)
    ]

    # Truncate with tight budget
    formatted = ChannelTranscriptFormatter.format_transcript(long_messages, max_tokens=100)

    # Must contain newest messages, but not all 50
    assert "tin nhắn thứ 49" in formatted
    assert "tin nhắn thứ 0" not in formatted


def test_context_builder_in_community_mode():
    builder = ContextBuilder()
    emotion = EmotionState(
        user_id=uuid4(),
        trust=0.70,
        attachment=0.30,
        comfort=0.60,
    )

    transcript = "[01:15] <Hoan>: Chisa ơi em thấy quán này thế nào?"
    result = builder.build(
        emotion=emotion,
        attachment_bonus=0.0,
        memories=["Hoan thích ăn đồ cay"],
        lore=["Quán ramen nằm gần viện nghiên cứu dữ liệu"],
        history=[],
        user_message="Chisa ơi em thấy quán này thế nào?",
        intent_name="LORE",
        budget_mode=BudgetMode.RAG,
        is_community=True,
        current_speaker_name="Hoan",
        channel_name="general-chat",
        guild_name="Chisa Server",
        channel_transcript=transcript,
    )

    prompt = result.prompt
    assert prompt is not None
    # Verify core persona is intact
    assert "Mutant Resonator" in prompt.system
    assert "Kuudere" in prompt.system
    # Verify community layered directive
    assert "#general-chat" in prompt.system
    assert "Chisa Server" in prompt.system
    assert "Hoan" in prompt.system
    assert "COMMUNITY CHANNEL ENVIRONMENT & GROUP RULES" in prompt.system
    # Verify transcript and memories
    assert "DIỄN BIẾN ĐOẠN CHAT GẦN ĐÂY TRONG KÊNH" in prompt.system
    assert transcript in prompt.system
    assert "Hoan thích ăn đồ cay" in prompt.system
    assert prompt.user_message == "[Hoan]: Chisa ơi em thấy quán này thế nào?"


@pytest.mark.asyncio
async def test_unified_chat_engine_community_mode_execution():
    mock_llm = MagicMock(spec=BaseLLMAdapter)
    mock_llm.generate = AsyncMock(
        return_value=LLMResponse(
            raw_content='{"response": "Quán đó tuyệt vời lắm đó Senpai!", "sentiment": {"reaction": "calm_warmth", "user_stance": "loving", "intensity": 0.7, "variance": 0.2}}',
            parsed={
                "response": "Quán đó tuyệt vời lắm đó Senpai!",
                "sentiment": {
                    "reaction": "calm_warmth",
                    "user_stance": "loving",
                    "intensity": 0.7,
                    "variance": 0.2,
                },
            },
            input_tokens=100,
            output_tokens=30,
        )
    )

    user_id = str(uuid4())
    user_uuid = uuid4()
    mock_stats = UserStats(user_id=user_uuid, interaction_count=5)
    initial_emotion = EmotionState(user_id=user_uuid, trust=0.50, attachment=0.10)

    mock_user_repo = MagicMock()
    mock_user_repo.get_or_create_user = AsyncMock()
    mock_user_repo.get_user_stats = AsyncMock(return_value=mock_stats)
    mock_user_repo.update_stats = AsyncMock()

    mock_emotion_repo = MagicMock()
    mock_emotion_repo.get_emotion_state = AsyncMock(return_value=initial_emotion)
    mock_emotion_repo.update_emotion = AsyncMock()

    mock_conv_repo = MagicMock()
    mock_conv_repo.get_or_create_conversation = AsyncMock(return_value=uuid4())
    mock_conv_repo.get_recent_history = AsyncMock(return_value=[])
    mock_conv_repo.get_latest_summary = AsyncMock(return_value=None)
    mock_conv_repo.save_message = AsyncMock()

    stages = [
        InitializationStage(
            user_repo_factory=lambda _: mock_user_repo,
            emotion_repo_factory=lambda _: mock_emotion_repo,
            conv_repo_factory=lambda _: mock_conv_repo,
        ),
        ContextBuildingStage(context_builder=ContextBuilder()),
        LLMGenerationStage(llm=mock_llm),
        EmotionUpdateStage(
            emotion_engine=EmotionEngine(),
            emotion_repo_factory=lambda _: mock_emotion_repo,
        ),
        PersistenceStage(
            user_repo_factory=lambda _: mock_user_repo,
            conv_repo_factory=lambda _: mock_conv_repo,
        ),
    ]

    pipeline = ChatPipeline(stages)
    mock_cache = MagicMock()
    mock_cache.acquire_lock = AsyncMock(return_value="token123")
    mock_cache.release_lock = AsyncMock()

    chat_engine = ChatEngine(
        pipeline=pipeline,
        uow_factory=lambda _: MagicMock(),
        cache_provider=mock_cache,
        emotion_repo_factory=lambda _: mock_emotion_repo,
        conv_repo_factory=lambda _: mock_conv_repo,
        user_repo_factory=lambda _: mock_user_repo,
        db_session_factory=lambda: AsyncMock(),
        llm=mock_llm,
        embedder=MagicMock(),
        vector_store=MagicMock(),
    )

    mock_session = MagicMock()
    mock_session.commit = AsyncMock()
    mock_session.rollback = AsyncMock()
    recent_messages = [
        CommunityMessage(
            message_id="1",
            speaker_id="user_123",
            speaker_name="Hoan",
            content="Chào Chisa",
            created_at=datetime.now(),
        )
    ]

    reply, updated_emotions = await chat_engine.community_chat(
        session=mock_session,
        channel_id="chan_123",
        user_id=user_id,
        user_message="Em có rảnh không?",
        speaker_name="Hoan",
        channel_name="gaming-lounge",
        guild_id="guild_456",
        guild_name="Anime Guild",
        recent_messages=recent_messages,
    )

    assert reply == "Quán đó tuyệt vời lắm đó Senpai!"
    assert updated_emotions["trust"] > 0.50
    mock_emotion_repo.update_emotion.assert_awaited_once()
    mock_user_repo.update_stats.assert_awaited_once()
    mock_conv_repo.save_message.assert_awaited()
