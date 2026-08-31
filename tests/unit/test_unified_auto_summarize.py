import sys
import os
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock

# Add project root to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.domain.services.chat_engine import ChatEngine
from app.domain.interfaces.llm_provider import LLMResponse


class DummyStats:
    def __init__(self, interaction_count: int = 50):
        self.interaction_count = interaction_count


class DummyUserRepo:
    def __init__(self, interaction_count: int = 50):
        self.interaction_count = interaction_count

    async def get_user_stats(self, user_uuid):
        return DummyStats(self.interaction_count)


class DummyConvRepo:
    def __init__(self, summary: str = "Previous summary: Senpai thích uống cà phê và làm dev."):
        self.summary = summary
        self.updated_summary = None

    async def get_latest_summary(self, user_uuid, conv_uuid):
        return self.summary

    async def get_recent_history(self, user_uuid, conv_uuid, limit=50):
        return [
            {"role": "user", "content": f"Tin nhắn đối thoại số {i}"}
            for i in range(1, 11)
        ]

    async def update_conversation_summary(self, conv_uuid, summary_text):
        self.updated_summary = summary_text


class DummyDbSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    async def commit(self):
        pass


@pytest.mark.asyncio
async def test_pure_auto_summarize_workflow():
    test_user_id = str(uuid.uuid4())
    test_conv_id = str(uuid.uuid4())

    # 1. Setup Mock Repos & Session
    dummy_conv_repo = DummyConvRepo(summary="Previous summary: Senpai thích uống cà phê và làm dev.")
    dummy_user_repo = DummyUserRepo(interaction_count=50)
    dummy_db_session = DummyDbSession()
    mock_cache = MagicMock()
    mock_cache.get = AsyncMock(return_value=None)
    mock_cache.set = AsyncMock()

    def db_session_factory():
        return dummy_db_session

    def conv_repo_factory(session):
        return dummy_conv_repo

    def user_repo_factory(session):
        return dummy_user_repo

    # 2. Setup Mock LLM Adapter
    mock_llm = MagicMock()
    mock_llm.generate = AsyncMock()
    mock_llm.generate.return_value = LLMResponse(
        raw_content='{"summary": "Senpai thích uống cà phê, làm dev và mới chia sẻ thêm sở thích đi phượt cùng Chisa."}',
        parsed={
            "summary": "Senpai thích uống cà phê, làm dev và mới chia sẻ thêm sở thích đi phượt cùng Chisa."
        },
        input_tokens=120,
        output_tokens=45,
        model="deepseek-v3",
        finish_reason="stop"
    )

    # 3. Instantiate ChatEngine
    engine = ChatEngine(
        pipeline=MagicMock(),
        uow_factory=MagicMock(),
        cache_provider=mock_cache,
        emotion_repo_factory=MagicMock(),
        conv_repo_factory=conv_repo_factory,
        user_repo_factory=user_repo_factory,
        db_session_factory=db_session_factory,
        llm=mock_llm,
        embedder=MagicMock(),
        vector_store=MagicMock()
    )

    # 4. Run Auto Summarize
    await engine._unified_auto_summarize(user_id=test_user_id, conv_id=test_conv_id)

    # 5. Verify Results
    assert mock_llm.generate.called
    assert dummy_conv_repo.updated_summary == "Senpai thích uống cà phê, làm dev và mới chia sẻ thêm sở thích đi phượt cùng Chisa."
    
    # Verify Redis summary sync
    assert mock_cache.set.called
    redis_set_args = mock_cache.set.call_args
    assert "chisa:user:" in redis_set_args[0][0]
    assert ":summary" in redis_set_args[0][0]
    assert redis_set_args[0][1] == "Senpai thích uống cà phê, làm dev và mới chia sẻ thêm sở thích đi phượt cùng Chisa."
