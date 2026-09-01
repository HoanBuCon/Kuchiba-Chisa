"""
Unit tests for CommunityTopicSummarizer with Redis Rolling Message Buffer.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.domain.services.community.topic_summarizer import CommunityTopicSummarizer
from app.domain.interfaces.llm_provider import LLMResponse


class InMemoryMockCache:
    def __init__(self):
        self.store = {}

    async def get(self, key: str):
        return self.store.get(key)

    async def set(self, key: str, value: str, ttl: int = None):
        self.store[key] = value

    async def get_json(self, key: str):
        return self.store.get(key)

    async def set_json(self, key: str, value: dict, ttl: int = None):
        self.store[key] = value

    async def delete(self, key: str):
        self.store.pop(key, None)

    async def delete_pattern(self, pattern: str):
        prefix = pattern.replace("*", "")
        keys_to_del = [k for k in self.store if prefix in k]
        for k in keys_to_del:
            self.store.pop(k, None)
        return len(keys_to_del)


@pytest.mark.asyncio
async def test_append_messages_accumulates_and_deduplicates():
    cache = InMemoryMockCache()
    mock_llm = MagicMock()
    summarizer = CommunityTopicSummarizer(llm=mock_llm, cache=cache)
    channel_id = "channel_test_123"

    # Turn 1: 3 channel messages + user turn + chisa reply
    messages_turn_1 = [
        {"speaker_name": "Nam", "content": "Tối nay mấy giờ mọi người?", "is_bot": False, "created_at": "14:00"},
        {"speaker_name": "Huy", "content": "Tầm 8h nhé", "is_bot": False, "created_at": "14:01"},
    ]
    user_turn_1 = {"speaker_name": "Minh", "content": "@Chisa em tham gia không?", "is_bot": False, "created_at": "14:02"}
    chisa_turn_1 = {"speaker_name": "Chisa", "content": "Em sẽ tham gia hỗ trợ buff ạ.", "is_bot": True, "created_at": "14:02"}

    await summarizer.append_messages(channel_id, messages_turn_1, user_turn_1, chisa_turn_1)

    buf1 = await summarizer.get_rolling_buffer(channel_id)
    assert len(buf1) == 4

    # Turn 2: Try appending duplicate messages + new messages
    messages_turn_2 = [
        {"speaker_name": "Huy", "content": "Tầm 8h nhé", "is_bot": False, "created_at": "14:01"},  # duplicate
        {"speaker_name": "Phong", "content": "Anh em nhớ mang đồ tank", "is_bot": False, "created_at": "14:05"},  # new
    ]
    user_turn_2 = {"speaker_name": "Phong", "content": "@Chisa mang healer nhé", "is_bot": False, "created_at": "14:06"}
    chisa_turn_2 = {"speaker_name": "Chisa", "content": "Vâng em đã chuẩn bị sẵn sàng.", "is_bot": True, "created_at": "14:06"}

    await summarizer.append_messages(channel_id, messages_turn_2, user_turn_2, chisa_turn_2)

    buf2 = await summarizer.get_rolling_buffer(channel_id)
    # 4 initial + 1 new channel msg + 1 user turn + 1 chisa turn = 7 (duplicate ignored)
    assert len(buf2) == 7
    contents = [m["content"] for m in buf2]
    assert contents.count("Tầm 8h nhé") == 1
    assert "Anh em nhớ mang đồ tank" in contents


@pytest.mark.asyncio
async def test_summarize_channel_topic_uses_rolling_buffer_and_trims():
    cache = InMemoryMockCache()
    mock_llm = MagicMock()
    mock_llm.generate = AsyncMock(
        return_value=LLMResponse(
            raw_content='{"topic_summary": "Nhóm thống nhất 8h tối lập đội săn Boss, Chisa tham gia hỗ trợ buff healer."}',
            parsed={"topic_summary": "Nhóm thống nhất 8h tối lập đội săn Boss, Chisa tham gia hỗ trợ buff healer."},
            input_tokens=100,
            output_tokens=50
        )
    )
    summarizer = CommunityTopicSummarizer(llm=mock_llm, cache=cache)
    channel_id = "channel_topic_999"
    guild_id = "guild_test_888"

    # Populate rolling buffer with 15 messages
    for i in range(15):
        await summarizer.append_messages(
            channel_id=channel_id,
            guild_id=guild_id,
            messages=[{"speaker_name": f"User_{i}", "content": f"Bàn luận chiến thuật trận {i}", "created_at": f"1{i}:00"}],
            current_user_turn={"speaker_name": f"User_{i}", "content": f"Câu hỏi {i}", "created_at": f"1{i}:01"},
            current_assistant_turn={"speaker_name": "Chisa", "content": f"Phản hồi {i}", "created_at": f"1{i}:01"}
        )

    buffer_before = await summarizer.get_rolling_buffer(channel_id, guild_id)
    assert len(buffer_before) > 15

    # Run summarize
    summary_result = await summarizer.summarize_channel_topic(
        channel_id=channel_id,
        guild_id=guild_id
    )

    assert summary_result is not None
    assert "săn Boss" in summary_result

    # Verify summary saved in Redis
    saved_summary = await summarizer.get_topic_summary(channel_id, guild_id)
    assert saved_summary == summary_result

    # Verify rolling buffer is trimmed to overlap size (10 messages)
    buffer_after = await summarizer.get_rolling_buffer(channel_id, guild_id)
    assert len(buffer_after) == summarizer.BUFFER_OVERLAP_MESSAGES
