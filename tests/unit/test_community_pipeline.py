from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
import pytest

from app.domain.entities.community import CommunityChatContext, CommunityMessage
from app.domain.entities.emotion import EmotionState
from app.domain.entities.user import UserStats
from app.domain.interfaces.llm_provider import BaseLLMAdapter, StructuredPrompt
from app.domain.services.budget_mode import BudgetMode
from app.domain.services.community.community_context_builder import CommunityContextBuilder
from app.domain.services.community.community_pipeline import CommunityChatPipeline
from app.domain.services.community.transcript_formatter import ChannelTranscriptFormatter
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

    # Truncate with very tight budget (e.g. 100 tokens)
    formatted = ChannelTranscriptFormatter.format_transcript(long_messages, max_tokens=100)

    # Must contain newest messages, but not all 50
    assert "tin nhắn thứ 49" in formatted
    assert "tin nhắn thứ 0" not in formatted


def test_community_context_builder():
    builder = CommunityContextBuilder()
    emotion = EmotionState(
        user_id=uuid4(),
        trust=0.70,
        attachment=0.30,
        comfort=0.60,
    )

    transcript = "[01:15] <Hoan>: Chisa ơi em thấy quán này thế nào?"
    result = builder.build(
        speaker_emotion=emotion,
        current_speaker_name="Hoan",
        channel_name="general-chat",
        guild_name="Chisa Server",
        transcript=transcript,
        user_message="Chisa ơi em thấy quán này thế nào?",
        memories=["Hoan thích ăn đồ cay"],
        lore=["Quán ramen nằm gần viện nghiên cứu dữ liệu"],
        budget_mode=BudgetMode.RAG,
    )

    prompt = result.prompt
    assert prompt is not None
    assert "#general-chat" in prompt.system
    assert "Chisa Server" in prompt.system
    assert "Hoan" in prompt.system
    assert "KỶ NIỆM VỀ HOAN" in prompt.system
    assert "Hoan thích ăn đồ cay" in prompt.system
    assert "KIẾN THỨC BỔ TRỢ & THẾ GIỚI" in prompt.system
    assert "Quán ramen nằm gần viện nghiên cứu" in prompt.system
    assert "DIỄN BIẾN ĐOẠN CHAT GẦN ĐÂY TRONG KÊNH" in prompt.system
    assert "[Hoan]: Chisa ơi em thấy quán này thế nào?" in prompt.user_message


@pytest.mark.asyncio
async def test_community_chat_pipeline_execution():
    mock_llm = MagicMock(spec=BaseLLMAdapter)
    mock_llm.generate = AsyncMock(
        return_value='{"response": "Quán đó tuyệt vời lắm đó Senpai!", "sentiment": {"reaction": "calm_warmth", "user_stance": "loving", "intensity": 0.7, "variance": 0.2}}'
    )

    pipeline = CommunityChatPipeline(
        llm=mock_llm,
        retrieval_pipeline=None,
        context_builder=CommunityContextBuilder(),
        emotion_engine=EmotionEngine(),
    )

    mock_session = MagicMock()
    mock_user_repo = MagicMock()
    mock_user_repo.get_or_create_user = AsyncMock()
    mock_user_repo.get_user_stats = AsyncMock(return_value=UserStats(user_id=uuid4(), interaction_count=5))
    mock_user_repo.increment_interaction_count = AsyncMock()

    mock_emotion_repo = MagicMock()
    speaker_id = str(uuid4())
    initial_emotion = EmotionState(user_id=uuid4(), trust=0.50, attachment=0.10)
    mock_emotion_repo.get_emotion_state = AsyncMock(return_value=initial_emotion)
    mock_emotion_repo.save_emotion_state = AsyncMock()

    recent_messages = [
        CommunityMessage(
            message_id="1",
            speaker_id="hoan_id",
            speaker_name="Hoan",
            content="Chào Chisa",
            created_at=datetime.now(),
        )
    ]

    context = await pipeline.execute(
        session=mock_session,
        channel_id="chan_123",
        guild_id="guild_456",
        channel_name="gaming-lounge",
        guild_name="Anime Guild",
        current_speaker_id=speaker_id,
        current_speaker_name="Hoan",
        user_message="Em có rảnh không?",
        recent_messages=recent_messages,
        user_repo=mock_user_repo,
        emotion_repo=mock_emotion_repo,
    )

    assert context.cleaned_response == "Quán đó tuyệt vời lắm đó Senpai!"
    assert context.extracted_sentiment["reaction"] == "calm_warmth"
    assert context.extracted_sentiment["user_stance"] == "loving"
    assert context.updated_speaker_emotions["trust"] > 0.50
    mock_emotion_repo.save_emotion_state.assert_awaited_once()
    mock_user_repo.increment_interaction_count.assert_awaited_once()
