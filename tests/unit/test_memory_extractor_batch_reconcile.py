import sys
import os
import uuid
import asyncio
from unittest.mock import AsyncMock, MagicMock

# Add project root to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.domain.services.memory_extractor import MemoryExtractor
from app.domain.interfaces.llm_provider import LLMResponse


async def test_batch_reconciliation_single_llm_call():
    print("=" * 65)
    print("TESTING BATCHED MEMORY RECONCILIATION SINGLE LLM CALL")
    print("=" * 65)

    # 1. Setup Mock LLM Adapter
    mock_llm = MagicMock()
    
    # Extraction response (Call 1): Returns 3 facts
    extract_response = LLMResponse(
        raw_content='{"facts": [{"type": "important_facts", "content": "Senpai vừa nhận việc tại Viettel", "importance_score": 0.95}, {"type": "preferences", "content": "Senpai thích uống matcha không đường", "importance_score": 0.8}, {"type": "relationship", "content": "Senpai gọi Chisa là Chisa-chan", "importance_score": 0.85}]}',
        parsed={
            "facts": [
                {"type": "important_facts", "content": "Senpai vừa nhận việc tại Viettel", "importance_score": 0.95},
                {"type": "preferences", "content": "Senpai thích uống matcha không đường", "importance_score": 0.8},
                {"type": "relationship", "content": "Senpai gọi Chisa là Chisa-chan", "importance_score": 0.85}
            ]
        },
        input_tokens=500,
        output_tokens=100,
        model="deepseek-v4-flash",
        finish_reason="stop"
    )

    # Batched Reconciliation response (Call 2): Resolves all 3 facts at once using candidate index mapping!
    reconcile_response = LLMResponse(
        raw_content='{"reconciliations": [{"index": 0, "action": "CONTRADICT", "conflicting_candidate_index": 0, "reasoning": "Job updated to Viettel"}, {"index": 1, "action": "DUPLICATE", "conflicting_candidate_index": null, "reasoning": "Already likes matcha"}, {"index": 2, "action": "KEEP_BOTH", "conflicting_candidate_index": null, "reasoning": "New nickname"}]}',
        parsed={
            "reconciliations": [
                {"index": 0, "action": "CONTRADICT", "conflicting_candidate_index": 0, "reasoning": "Job updated to Viettel"},
                {"index": 1, "action": "DUPLICATE", "conflicting_candidate_index": None, "reasoning": "Already likes matcha"},
                {"index": 2, "action": "KEEP_BOTH", "conflicting_candidate_index": None, "reasoning": "New nickname"}
            ]
        },
        input_tokens=400,
        output_tokens=120,
        model="deepseek-v4-flash",
        finish_reason="stop"
    )

    # LLM will be called twice in total: 1 for extraction, 1 for batched reconciliation
    mock_llm.generate = AsyncMock(side_effect=[extract_response, reconcile_response])

    # 2. Setup Mock Embedder & Vector Store
    mock_embedder = MagicMock()
    mock_embedder.embed_text = AsyncMock(return_value=[0.1] * 768)

    # Mock Qdrant returning existing candidates for all 3 facts
    mock_vector_store = MagicMock()
    mock_vector_store.search_by_user = AsyncMock(side_effect=[
        [{"id": "old-job-id-123", "payload": {"text_content": "Senpai đang phỏng vấn FPT"}}],
        [{"id": "old-matcha-id-456", "payload": {"text_content": "Senpai thích uống matcha"}}],
        [{"id": "old-nick-id-789", "payload": {"text_content": "Senpai gọi Chisa là em Chisa"}}]
    ])
    mock_vector_store.upsert_memory = AsyncMock()
    mock_vector_store.delete_points = AsyncMock()

    # 3. Instantiate MemoryExtractor
    extractor = MemoryExtractor(llm=mock_llm, embedder=mock_embedder, vector_store=mock_vector_store)

    # 4. Execute extract_and_store_batch
    user_id = str(uuid.uuid4())
    conv_id = str(uuid.uuid4())
    history = [
        {"role": "user", "content": "anh vừa đỗ Viettel rồi"},
        {"role": "assistant", "content": "Chúc mừng Senpai nhé!"}
    ]
    
    print("[>] Running extract_and_store_batch with 3 facts having Qdrant candidates...")
    await extractor.extract_and_store_batch(
        user_id=user_id,
        conversation_id=conv_id,
        history=history,
        current_user_message="anh chuyển sang uống matcha không đường nè, gọi em là Chisa-chan nha",
        current_assistant_reply="Dạ vâng ạ Chisa-chan nghe dễ thương ghê!"
    )

    # 5. Assertions
    print("\n[VERIFICATION]")
    print(f"Total LLM generate calls: {mock_llm.generate.call_count}")
    # MUST BE EXACTLY 2 LLM CALLS: 1 for extraction + 1 for ALL 3 reconciliations batched!
    assert mock_llm.generate.call_count == 2, f"Expected 2 LLM calls, got {mock_llm.generate.call_count}"
    print("  [OK] LLM was called exactly 2 times (1 extract + 1 batched reconciliation)!")

    # Verify conflict deleted
    assert mock_vector_store.delete_points.called
    del_ids = mock_vector_store.delete_points.call_args.kwargs.get("ids")
    print(f"  [OK] Superseded memory deleted from Qdrant: {del_ids}")
    assert del_ids == ["old-job-id-123"]

    # Verify upserts: Fact 0 (Viettel) upserted, Fact 1 (matcha duplicate) skipped, Fact 2 (nickname) upserted
    # Total upserts = 2 (Fact 0 and Fact 2)
    assert mock_vector_store.upsert_memory.call_count == 2
    print(f"  [OK] Qdrant upserts count: {mock_vector_store.upsert_memory.call_count} (Fact 0 & Fact 2, Fact 1 duplicate was skipped)!")

    print("\n" + "=" * 65)
    print("BATCHED RECONCILIATION TEST PASSED 100%!")
    print("=" * 65)


if __name__ == "__main__":
    asyncio.run(test_batch_reconciliation_single_llm_call())
