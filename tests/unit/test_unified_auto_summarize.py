import sys
import os
import uuid
import asyncio
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


async def run_unified_auto_summarize_test():
    print("=" * 65)
    print("MOP HONG KIEM THU UNIFIED AUTO SUMMARIZE WORKFLOW")
    print("=" * 65)

    test_user_id = str(uuid.uuid4())
    test_conv_id = str(uuid.uuid4())

    # 1. Setup Mock Repos & Session
    dummy_conv_repo = DummyConvRepo(summary="Previous summary: Senpai thích uống cà phê và làm dev.")
    dummy_user_repo = DummyUserRepo(interaction_count=50)
    dummy_db_session = DummyDbSession()

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
        raw_content='{"summary": "Senpai thích uống cà phê, làm dev và mới chia sẻ thêm sở thích đi phượt.", "extracted_facts": [{"type": "preferences", "content": "Senpai thích đi phượt vào cuối tuần", "importance_score": 0.8}]}',
        parsed={
            "summary": "Senpai thích uống cà phê, làm dev và mới chia sẻ thêm sở thích đi phượt.",
            "extracted_facts": [
                {
                    "type": "preferences",
                    "content": "Senpai thích đi phượt vào cuối tuần",
                    "importance_score": 0.8
                }
            ]
        },
        input_tokens=150,
        output_tokens=80,
        model="deepseek-v3",
        finish_reason="stop"
    )

    # 3. Setup Mock Embedder & Vector Store
    mock_embedder = MagicMock()
    mock_embedder.embed_text = AsyncMock(return_value=[0.1] * 768)

    mock_vector_store = MagicMock()
    mock_vector_store.search_by_user = AsyncMock(return_value=[])  # No duplicate candidate
    mock_vector_store.upsert_memory = AsyncMock()
    mock_vector_store.delete_points = AsyncMock()

    # 4. Instantiate ChatEngine
    engine = ChatEngine(
        pipeline=MagicMock(),
        uow_factory=MagicMock(),
        cache_provider=MagicMock(),
        emotion_repo_factory=MagicMock(),
        conv_repo_factory=conv_repo_factory,
        user_repo_factory=user_repo_factory,
        db_session_factory=db_session_factory,
        llm=mock_llm,
        embedder=mock_embedder,
        vector_store=mock_vector_store
    )

    # 5. Run Unified Auto Summarize
    print(f"[>] Triggering _unified_auto_summarize for User: {test_user_id}...")
    await engine._unified_auto_summarize(user_id=test_user_id, conv_id=test_conv_id)

    # 6. Verify Results
    print("\n[RESULT CHECK]")
    
    # Task 1 Check
    print("\n[Task 1: Cap nhat PostgreSQL Conversations.summary]")
    print(f"  - LLM Called: {mock_llm.generate.called}")
    print(f"  - Summary moi luu PostgreSQL: \"{dummy_conv_repo.updated_summary}\"")
    assert dummy_conv_repo.updated_summary == "Senpai thích uống cà phê, làm dev và mới chia sẻ thêm sở thích đi phượt."
    print("  [OK] Task 1 PASSED!")

    # Task 2 Check
    print("\n[Task 2: Trich xuat & Conflict-Check Ky uc cho Qdrant Vector DB]")
    print(f"  - Embedder Called: {mock_embedder.embed_text.called}")
    print(f"  - Qdrant Search Called: {mock_vector_store.search_by_user.called}")
    print(f"  - Qdrant Upsert Called: {mock_vector_store.upsert_memory.called}")
    
    assert mock_vector_store.upsert_memory.called
    upsert_args = mock_vector_store.upsert_memory.call_args.kwargs
    payload = upsert_args.get("payload")
    print(f"  - Qdrant Upserted Payload Content: \"{payload.text_content}\" (Type: {payload.memory_type})")
    assert payload.text_content == "Senpai thích đi phượt vào cuối tuần"
    assert payload.memory_type == "preferences"
    print("  [OK] Task 2 PASSED!")

    print("\n" + "=" * 65)
    print("ALL SIMULATION STEPS COMPLETED SUCCESSFULLY 100%!")
    print("=" * 65)


if __name__ == "__main__":
    asyncio.run(run_unified_auto_summarize_test())
