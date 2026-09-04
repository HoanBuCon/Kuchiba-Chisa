import pytest
import time
from unittest.mock import AsyncMock, MagicMock
from app.domain.entities.memory import MemoryPayload, GuildMemoryPayload
from app.domain.services.rag.retriever_guild_memory import GuildMemoryRetriever
from app.domain.services.community.transcript_formatter import ChannelTranscriptFormatter
from app.domain.services.community.topic_summarizer import CommunityTopicSummarizer
from app.domain.services.context_builder import ContextBuilder
from app.domain.entities.emotion import EmotionState


@pytest.mark.asyncio
async def test_guild_memory_payload_creation():
    payload = GuildMemoryPayload(
        text_content="Server sẽ tổ chức giải đấu Honkai vào thứ Bảy.",
        guild_id="guild_123",
        channel_id="chan_456",
        memory_type="guild_event",
        expires_at=1770000000,
        recorded_by_speaker="KuroSenpai",
        created_at=int(time.time())
    )
    assert payload.text_content == "Server sẽ tổ chức giải đấu Honkai vào thứ Bảy."
    assert payload.guild_id == "guild_123"
    assert payload.channel_id == "chan_456"
    assert payload.memory_type == "guild_event"
    assert payload.expires_at == 1770000000
    assert payload.recorded_by_speaker == "KuroSenpai"


@pytest.mark.asyncio
async def test_guild_memory_retriever_recency_and_decay():
    mock_vector_store = AsyncMock()
    
    # Mock payload from Qdrant
    recent_time = time.time()
    old_time = recent_time - (7 * 86400) # 7 days ago
    
    mock_item_1 = {
        "text": "Server có văn hóa chào hỏi bằng emote Chisa mỗi sáng.",
        "score": 0.85,
        "metadata": {
            "created_at": recent_time,
            "guild_id": "guild_123",
            "channel_id": "chan_456",
            "memory_type": "guild_culture",
            "expires_at": None,
        }
    }
    mock_item_2 = {
        "text": "Sự kiện raid boss tuần trước đã kết thúc.",
        "score": 0.82,
        "metadata": {
            "created_at": old_time,
            "guild_id": "guild_123",
            "channel_id": "chan_456",
            "memory_type": "guild_event",
            "expires_at": None,
        }
    }
    
    mock_vector_store.search_guild_memories.return_value = [mock_item_1, mock_item_2]
    
    retriever = GuildMemoryRetriever(vector_store=mock_vector_store)
    results = await retriever.retrieve_guild_memories(
        collection="guild_memories",
        query_vector=[0.1] * 384,
        guild_id="guild_123",
        channel_id="chan_456",
        limit=10,
        top_k=5
    )
    
    assert len(results) == 2
    # Item 1 is recent -> higher hybrid score
    assert results[0].text_content == "Server có văn hóa chào hỏi bằng emote Chisa mỗi sáng."
    assert results[0].metadata["guild_id"] == "guild_123"
    assert results[0].final_score > results[1].final_score


@pytest.mark.asyncio
async def test_channel_transcript_formatter_smart_compression():
    raw_messages = [
        {"speaker_name": "UserA", "content": "!play yoasobi", "created_at": "2026-08-30 20:00:00"},
        {"speaker_name": "UserA", "content": "!skip", "created_at": "2026-08-30 20:00:05"},
        {"speaker_name": "UserA", "content": "Tối nay ai leo tháp không?", "created_at": "2026-08-30 20:00:10"},
        {"speaker_name": "UserA", "content": "Tôi đang rảnh nè.", "created_at": "2026-08-30 20:00:15"},
        {"speaker_name": "UserB", "content": "Để tôi vào chung team với!", "created_at": "2026-08-30 20:00:30"},
        {"speaker_name": "UserB", "content": "c!help", "created_at": "2026-08-30 20:00:35"},
    ]
    
    # 1. Test compression & coalescing
    coalesced, stats = ChannelTranscriptFormatter.compress_messages(raw_messages)
    assert stats["raw_count"] == 6
    assert stats["filtered_commands"] == 3  # !play, !skip, c!help
    assert stats["compressed_count"] == 2   # 1 for UserA (2 lines), 1 for UserB (1 line)
    
    # UserA lines should be coalesced
    assert "Tối nay ai leo tháp không?\n  Tôi đang rảnh nè." in coalesced[0]
    assert "Để tôi vào chung team với!" in coalesced[1]
    
    # 2. Test formatted transcript output
    transcript = ChannelTranscriptFormatter.format_transcript(raw_messages, max_tokens=1000)
    assert "!play" not in transcript
    assert "!skip" not in transcript
    assert "c!help" not in transcript
    assert "<UserA>" in transcript
    assert "<UserB>" in transcript

    # 3. Test filtering of other third-party bots and Chisa's own command announcements
    bot_and_announcement_messages = [
        {"speaker_name": "Carl-bot", "content": "Welcome @UserC to the server!", "is_bot": True, "created_at": "2026-08-30 20:01:00"},
        {"speaker_name": "Midjourney", "content": "Image rendering complete.", "is_bot": True, "created_at": "2026-08-30 20:01:05"},
        {"speaker_name": "Chisa", "content": "**NUKE SERVER THÀNH CÔNG!**\nToàn bộ Ký ức Cộng đồng đã dọn sạch.", "is_bot": True, "created_at": "2026-08-30 20:01:10"},
        {"speaker_name": "Chisa", "content": "💥 **ĐÃ XÓA KÝ ỨC CÁ NHÂN CỦA BẠN!**", "is_bot": True, "created_at": "2026-08-30 20:01:15"},
        {"speaker_name": "Chisa", "content": "Chào Senpai, em có thể giúp gì cho Senpai ạ?", "is_bot": True, "created_at": "2026-08-30 20:01:20"},
        {"speaker_name": "UserC", "content": "Em thấy boss hôm nay thế nào?", "is_bot": False, "created_at": "2026-08-30 20:01:25"},
    ]
    coalesced_bot, stats_bot = ChannelTranscriptFormatter.compress_messages(bot_and_announcement_messages)
    assert stats_bot["filtered_commands"] == 4  # Carl-bot, Midjourney, Chisa NUKE, Chisa Xóa Ký ức
    assert stats_bot["compressed_count"] == 2   # 1 for Chisa conversational reply, 1 for UserC
    
    transcript_bot = ChannelTranscriptFormatter.format_transcript(bot_and_announcement_messages)
    assert "Carl-bot" not in transcript_bot
    assert "Midjourney" not in transcript_bot
    assert "NUKE SERVER THÀNH CÔNG" not in transcript_bot
    assert "ĐÃ XÓA KÝ ỨC" not in transcript_bot
    assert "Chào Senpai, em có thể giúp gì cho Senpai ạ?" in transcript_bot
    assert "Em thấy boss hôm nay thế nào?" in transcript_bot


@pytest.mark.asyncio
async def test_community_topic_summarizer():
    mock_llm = AsyncMock()
    mock_cache = AsyncMock()
    
    # Simulate Redis get & set
    cache_store = {}
    async def fake_get(key):
        return cache_store.get(key)
    async def fake_set(key, val, ttl=None):
        cache_store[key] = val
        return True
        
    mock_cache.get.side_effect = fake_get
    mock_cache.set.side_effect = fake_set
    
    mock_response = MagicMock()
    mock_response.parsed = {
        "topic_summary": "Nhóm đang thảo luận về việc lập team leo tháp và lên lịch đi raid boss tối nay."
    }
    mock_llm.generate.return_value = mock_response
    
    summarizer = CommunityTopicSummarizer(llm=mock_llm, cache=mock_cache)
    
    # Test message counter increment
    c1 = await summarizer.increment_message_count("chan_999")
    assert c1 == 1
    c2 = await summarizer.increment_message_count("chan_999")
    assert c2 == 2
    
    # Test summarization
    messages = [
        {"speaker_name": "UserA", "content": "Tối nay ai đi raid không?", "created_at": "20:00"},
        {"speaker_name": "UserB", "content": "8h tối nhé mọi người.", "created_at": "20:01"},
    ]
    summary = await summarizer.summarize_channel_topic(
        channel_id="chan_999",
        guild_id="guild_888",
        messages=messages
    )
    assert summary == "Nhóm đang thảo luận về việc lập team leo tháp và lên lịch đi raid boss tối nay."
    
    # Test get summary
    cached_summary = await summarizer.get_topic_summary("chan_999", "guild_888")
    assert cached_summary == summary


@pytest.mark.asyncio
async def test_context_builder_with_guild_memories_and_topic_summary():
    import uuid
    builder = ContextBuilder()
    emotion = EmotionState(user_id=uuid.uuid4(), joy=0.5, trust=0.6, irritation=0.1, sadness=0.0, attachment=0.4)
    
    result = builder.build(
        emotion=emotion,
        attachment_bonus=0.0,
        memories=["User thích uống trà xanh."],
        lore=["Kuchiba Chisa là AI companion."],
        history=[{"role": "user", "content": "Chào em"}],
        user_message="Tối nay có lịch gì trong server không?",
        intent_name="COMMUNITY_CHAT",
        is_community=True,
        current_speaker_name="KuroSenpai",
        channel_name="general",
        guild_name="Chisa Lounge",
        topic_summary="Nhóm đang bàn luận về giải đấu game cuối tuần.",
        guild_memories=["Server sẽ tổ chức giải đấu Honkai vào thứ Bảy lúc 20:00."],
    )
    
    system_text = result.prompt.system
    # Verify topic summary block
    assert "[BỐI CẢNH THẢO LUẬN GẦN ĐÂY CỦA NHÓM]" in system_text
    assert "Nhóm đang bàn luận về giải đấu game cuối tuần." in system_text
    
    # Verify server knowledge block
    assert "[TRI THỨC & SỰ KIỆN CHUNG CỦA SERVER]" in system_text
    assert "Server sẽ tổ chức giải đấu Honkai vào thứ Bảy lúc 20:00." in system_text
    
    # Verify user memory block
    assert "[MEMORIES — REFERENCE DATA START]" in system_text
    assert "User thích uống trà xanh." in system_text
