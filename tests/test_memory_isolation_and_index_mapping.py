"""
================================================================================
VERIFICATION TEST SUITE:
1. Candidate Index/Reference Mapping for Memory Conflict Resolution.
2. Strict Long-Term Memory Isolation Between Conversations (Conversation-Scoped LTM).
================================================================================
Output: Detailed logs and assertions written to tests/logs/memory_verification_report.log
================================================================================
"""

import sys
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import asyncio
import time
import uuid
from typing import Dict, List, Any
from unittest.mock import AsyncMock, MagicMock

from app.domain.services.memory_extractor import MemoryExtractor
from app.domain.entities.memory import MemoryPayload
from app.domain.interfaces.llm_provider import LLMResponse
from app.domain.services.rag.retriever_memory import MemoryRetriever
from app.infrastructure.vector.qdrant.qdrant_service import qdrant_service


class TestLogger:
    def __init__(self, log_path: str):
        self.log_path = log_path
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        # Clear previous log
        with open(self.log_path, "w", encoding="utf-8") as f:
            f.write(f"=== CHISA MEMORY VERIFICATION TEST REPORT ===\n")
            f.write(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")

    def log(self, text: str = ""):
        print(text)
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(text + "\n")


logger = TestLogger(os.path.join(PROJECT_ROOT, "tests", "logs", "memory_verification_report.log"))


# ==============================================================================
# TEST PART 1: Candidate Index/Reference Mapping Verification
# ==============================================================================
async def verify_candidate_index_mapping():
    logger.log("=" * 80)
    logger.log("🧪 TEST PART 1: VERIFY CANDIDATE INDEX REFERENCE MAPPING ([cand_0], [cand_1]...)")
    logger.log("=" * 80)

    # 1. Setup candidate memories with realistic UUIDs
    cand_fpt_id = f"fpt-job-uuid-{uuid.uuid4().hex[:8]}"
    cand_coffee_id = f"coffee-uuid-{uuid.uuid4().hex[:8]}"
    cand_nickname_id = f"nickname-uuid-{uuid.uuid4().hex[:8]}"

    candidates_item_0 = [
        {"id": cand_fpt_id, "payload": {"text_content": "Senpai đang phỏng vấn vị trí Backend tại FPT Hà Nội"}},
        {"id": cand_coffee_id, "payload": {"text_content": "Senpai thích uống cà phê đen đậm đặc buổi sáng"}}
    ]

    candidates_item_1 = [
        {"id": cand_nickname_id, "payload": {"text_content": "Senpai muốn Chisa gọi là Senpai-chan"}}
    ]

    items_to_reconcile = [
        {
            "index": 0,
            "content": "Senpai đã chuyển vào Sài Gòn và chính thức nhận việc AI Engineer tại VNG",
            "candidates": candidates_item_0
        },
        {
            "index": 1,
            "content": "Senpai rất thích Chisa gọi là Senpai-chan mỗi khi chào buổi sáng",
            "candidates": candidates_item_1
        }
    ]

    logger.log("📋 [Input Candidates to Reconcile]:")
    logger.log(f"  Fact 0 Candidates:")
    logger.log(f"    - [cand_0] ID: {cand_fpt_id} | 'Senpai đang phỏng vấn FPT Hà Nội'")
    logger.log(f"    - [cand_1] ID: {cand_coffee_id} | 'Senpai thích uống cà phê đen'")
    logger.log(f"  Fact 1 Candidates:")
    logger.log(f"    - [cand_0] ID: {cand_nickname_id} | 'Senpai muốn Chisa gọi là Senpai-chan'")

    # 2. Mock LLM returning index references instead of raw UUIDs
    mock_llm = MagicMock()
    mock_llm.generate = AsyncMock(return_value=LLMResponse(
        raw_content="""{
            "reconciliations": [
                {
                    "index": 0,
                    "action": "CONTRADICT",
                    "conflicting_candidate_index": 0,
                    "reasoning": "New fact (VNG AI Engineer) supersedes old FPT interview status [cand_0]."
                },
                {
                    "index": 1,
                    "action": "DUPLICATE",
                    "conflicting_candidate_index": null,
                    "reasoning": "Nickname is already registered [cand_0]."
                }
            ]
        }""",
        parsed={
            "reconciliations": [
                {
                    "index": 0,
                    "action": "CONTRADICT",
                    "conflicting_candidate_index": 0,
                    "reasoning": "New fact (VNG AI Engineer) supersedes old FPT interview status [cand_0]."
                },
                {
                    "index": 1,
                    "action": "DUPLICATE",
                    "conflicting_candidate_index": None,
                    "reasoning": "Nickname is already registered [cand_0]."
                }
            ]
        },
        input_tokens=320,
        output_tokens=95,
        model="deepseek-v4-flash",
        finish_reason="stop"
    ))

    # 3. Instantiate extractor and call reconcile_memory_conflicts_batch
    mock_embedder = MagicMock()
    mock_vector_store = MagicMock()

    extractor = MemoryExtractor(llm=mock_llm, embedder=mock_embedder, vector_store=mock_vector_store)

    logger.log("\n🤖 [Executing reconcile_memory_conflicts_batch with LLM Prompt]...")
    results = await extractor.reconcile_memory_conflicts_batch(items_to_reconcile)

    # 4. Verify the mapped results
    logger.log("\n🎯 [Verification Results]:")
    logger.log(f"  Fact 0 Result: {results.get(0)}")
    logger.log(f"  Fact 1 Result: {results.get(1)}")

    action_0, conflicting_id_0 = results[0]
    action_1, conflicting_id_1 = results[1]

    # Assert Fact 0 mapped [cand_0] to cand_fpt_id
    assert action_0 == "CONTRADICT", f"Expected CONTRADICT, got {action_0}"
    assert conflicting_id_0 == cand_fpt_id, f"Expected {cand_fpt_id}, got {conflicting_id_0}"
    logger.log(f"  ✅ [PASS] Fact 0 correctly mapped 'conflicting_candidate_index: 0' -> Real ID: '{conflicting_id_0}'")

    # Assert Fact 1 is DUPLICATE with null conflicting_id
    assert action_1 == "DUPLICATE", f"Expected DUPLICATE, got {action_1}"
    assert conflicting_id_1 is None, f"Expected None, got {conflicting_id_1}"
    logger.log(f"  ✅ [PASS] Fact 1 correctly recognized DUPLICATE with conflicting_id=None")

    logger.log("\n✨ PART 1: CANDIDATE INDEX MAPPING TEST COMPLETED 100% SUCCESSFULLY!\n")


# ==============================================================================
# TEST PART 2: Memory Isolation Between Conversations (Conversation-Scoped LTM)
# ==============================================================================
async def verify_conversation_memory_isolation():
    logger.log("=" * 80)
    logger.log("🧪 TEST PART 2: VERIFY LONG-TERM MEMORY ISOLATION BETWEEN CONVERSATIONS")
    logger.log("=" * 80)

    # Unique test user and two distinct conversations
    test_user_id = f"test_iso_user_{uuid.uuid4().hex[:6]}"
    conv_id_1 = f"conv_server_A_{uuid.uuid4().hex[:6]}"
    conv_id_2 = f"conv_server_B_{uuid.uuid4().hex[:6]}"

    logger.log(f"👤 User ID        : {test_user_id}")
    logger.log(f"💬 Conversation 1 : {conv_id_1} (e.g. Server Discord A)")
    logger.log(f"💬 Conversation 2 : {conv_id_2} (e.g. Server Discord B)")
    logger.log("-" * 80)

    # FastEmbed vectors (dummy or real embedder)
    from app.infrastructure.embeddings.fastembed_adapter import FastEmbedAdapter
    embedder = FastEmbedAdapter()
    retriever = MemoryRetriever(vector_store=qdrant_service)

    # ── Step 1: Store Memory in Conversation 1 ──
    fact_conv_1 = "Senpai thích uống trà hoa cúc mật ong vào mỗi buổi sáng"
    logger.log(f"📌 [Action 1] Storing memory into Conversation 1 ({conv_id_1}):")
    logger.log(f"   Content: \"{fact_conv_1}\"")

    vec_1 = await embedder.embed_text(fact_conv_1, prefix="passage: ")
    point_id_1 = str(uuid.uuid4())
    payload_1 = MemoryPayload(
        user_id=test_user_id,
        conversation_id=conv_id_1,
        memory_type="preferences",
        importance_score=0.9,
        created_at=int(time.time()),
        text_content=fact_conv_1,
    )
    await qdrant_service.upsert_memory(
        collection="memories",
        point_id=point_id_1,
        vector=vec_1,
        payload=payload_1
    )
    logger.log(f"   -> Upserted to Qdrant successfully (Point ID: {point_id_1})")

    # ── Step 2: Query from Conversation 1 ──
    query_text = "Senpai thích uống đồ uống gì vào buổi sáng?"
    query_vec = await embedder.embed_text(query_text, prefix="query: ")
    
    logger.log(f"\n🔍 [Query Test 1] Querying with conv_id = {conv_id_1}...")
    memories_in_conv_1 = await retriever.retrieve_memories(
        collection="memories",
        query_vector=query_vec,
        user_id=test_user_id,
        conversation_id=conv_id_1,
        limit=5
    )
    logger.log(f"   Found {len(memories_in_conv_1)} memories in Conversation 1:")
    for m in memories_in_conv_1:
        logger.log(f"   - [Score {m.final_score:.3f}] \"{m.text_content}\" (Type: {m.memory_type})")

    assert len(memories_in_conv_1) >= 1, "Expected at least 1 memory in Conversation 1"
    assert memories_in_conv_1[0].text_content == fact_conv_1
    logger.log("   ✅ [PASS] Conversation 1 successfully retrieved its own memory!")

    # ── Step 3: Query SAME user but with Conversation 2 (Must be EMPTY!) ──
    logger.log(f"\n🔍 [Isolation Test] Querying SAME query with conv_id = {conv_id_2} (Conversation 2)...")
    memories_in_conv_2 = await retriever.retrieve_memories(
        collection="memories",
        query_vector=query_vec,
        user_id=test_user_id,
        conversation_id=conv_id_2,
        limit=5
    )
    logger.log(f"   Found {len(memories_in_conv_2)} memories in Conversation 2")

    assert len(memories_in_conv_2) == 0, f"Expected 0 memories in Conversation 2, but found {len(memories_in_conv_2)}! Isolation failed."
    logger.log("   ✅ [PASS] Conversation 2 returned 0 memories! Strict isolation verified.")

    # ── Step 4: Store a DIFFERENT Memory in Conversation 2 ──
    fact_conv_2 = "Senpai chuyển sang lập trình full-time Rust và Python"
    logger.log(f"\n📌 [Action 2] Storing memory into Conversation 2 ({conv_id_2}):")
    logger.log(f"   Content: \"{fact_conv_2}\"")

    vec_2 = await embedder.embed_text(fact_conv_2, prefix="passage: ")
    point_id_2 = str(uuid.uuid4())
    payload_2 = MemoryPayload(
        user_id=test_user_id,
        conversation_id=conv_id_2,
        memory_type="important_facts",
        importance_score=0.95,
        created_at=int(time.time()),
        text_content=fact_conv_2,
    )
    await qdrant_service.upsert_memory(
        collection="memories",
        point_id=point_id_2,
        vector=vec_2,
        payload=payload_2
    )
    logger.log(f"   -> Upserted to Qdrant successfully (Point ID: {point_id_2})")

    # ── Step 5: Cross-check Bidirectional Isolation ──
    tech_query = "Ngôn ngữ lập trình của Senpai là gì?"
    tech_vec = await embedder.embed_text(tech_query, prefix="query: ")

    logger.log(f"\n🔍 [Bidirectional Isolation Check] Querying tech stack in Conversation 1 vs 2:")
    
    res_conv_1_tech = await retriever.retrieve_memories(
        collection="memories",
        query_vector=tech_vec,
        user_id=test_user_id,
        conversation_id=conv_id_1,
        limit=5
    )
    logger.log(f"   Conversation 1 results for tech query: {len(res_conv_1_tech)} items")
    for m in res_conv_1_tech:
        logger.log(f"   - Conv 1 returned: \"{m.text_content}\"")
        assert m.text_content != fact_conv_2, "LEAK ERROR: Conversation 1 leaked Conversation 2's tech memory!"
    logger.log("   ✅ [PASS] Conversation 1 did NOT leak Conversation 2's tech memory!")

    res_conv_2_tech = await retriever.retrieve_memories(
        collection="memories",
        query_vector=tech_vec,
        user_id=test_user_id,
        conversation_id=conv_id_2,
        limit=5
    )
    logger.log(f"   Conversation 2 results for tech query: {len(res_conv_2_tech)} items")
    for m in res_conv_2_tech:
        logger.log(f"   - Conv 2 returned: \"{m.text_content}\"")
        assert m.text_content != fact_conv_1, "LEAK ERROR: Conversation 2 leaked Conversation 1's tea memory!"

    assert any(m.text_content == fact_conv_2 for m in res_conv_2_tech), "Conversation 2 MUST find its own tech memory!"
    logger.log("   ✅ [PASS] Conversation 2 successfully found its own tech memory and did NOT leak Conversation 1's memory!")
    assert len(res_conv_2_tech) >= 1, "Conversation 2 MUST find its own tech memory"
    assert res_conv_2_tech[0].text_content == fact_conv_2
    logger.log(f"   - Found: \"{res_conv_2_tech[0].text_content}\"")
    logger.log("   ✅ [PASS] Bidirectional memory isolation is 100% verified!")

    # ── Clean up test data from Qdrant ──
    await qdrant_service.delete_points("memories", [point_id_1, point_id_2])
    logger.log(f"\n🧹 [Cleanup] Deleted test points from Qdrant: [{point_id_1}, {point_id_2}]")
    logger.log("\n✨ PART 2: CONVERSATION ISOLATION TEST COMPLETED 100% SUCCESSFULLY!\n")


# ==============================================================================
# MAIN RUNNER
# ==============================================================================
async def main():
    logger.log("🚀 STARTING MEMORY VERIFICATION TEST SUITE...")
    start_time = time.time()

    try:
        await verify_candidate_index_mapping()
        await verify_conversation_memory_isolation()
        
        total_time = time.time() - start_time
        logger.log("=" * 80)
        logger.log(f"🎉 ALL TESTS PASSED SUCCESSFULLY IN {total_time:.2f}s!")
        logger.log(f"📄 Full test log written to: {logger.log_path}")
        logger.log("=" * 80)
    except Exception as e:
        logger.log(f"\n❌ TEST FAILED WITH EXCEPTION: {e}")
        import traceback
        logger.log(traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
