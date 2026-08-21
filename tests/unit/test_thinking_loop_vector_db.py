import sys
from pathlib import Path

# Add project root directory to sys.path so it can be run directly with `python`
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import pytest
from unittest.mock import AsyncMock, MagicMock
from app.domain.services.rag.thinking_loop import ThinkingLoopAgent
from app.domain.services.rag.pipeline import RAGPipeline
from app.domain.interfaces.llm_provider import LLMResponse


class DummyTracker:
    def __init__(self):
        self.steps = []

    def add_step(self, name, stage_id="stage_5_rag", depth=1, category="test", title="", subtitle="", data=None, **kwargs):
        self.steps.append({
            "name": name,
            "stage_id": stage_id,
            "depth": depth,
            "category": category,
            "title": title,
            "subtitle": subtitle,
            "data": data or {},
        })


class DummyEmbedder:
    def __init__(self):
        self.calls = []

    async def embed_text(self, text: str, prefix: str = ""):
        self.calls.append((text, prefix))
        return [0.1, 0.2, 0.3]


class DummyLoreRetriever:
    def __init__(self, return_data=None):
        self.calls = []
        self.return_data = return_data if return_data is not None else [
            ("Kuchiba Chisa là một cộng sự AI thân thiết đồng hành cùng Senpai.", 0.85, {"source": "character_lore"})
        ]

    async def retrieve_lore_parent_child(self, collection, query_vector, session=None, query_text="", top_k=3, score_threshold=0.30, **kwargs):
        self.calls.append({
            "collection": collection,
            "query_vector": query_vector,
            "query_text": query_text,
            "top_k": top_k,
            "score_threshold": score_threshold,
            "kwargs": kwargs,
        })
        if isinstance(self.return_data, dict):
            return self.return_data.get(collection, [])
        return self.return_data


class DummyLLM:
    def __init__(self, parsed_response=None):
        self.calls = []
        self.parsed_response = parsed_response or {
            "has_enough_info": False,
            "search_query": "kỹ năng của Kuchiba Chisa",
            "search_target": "vector",
            "distilled_facts": "Chisa là AI companion",
        }

    async def generate(self, prompt, **kwargs):
        self.calls.append(prompt)
        return LLMResponse(
            text="{}",
            raw_content="{}",
            parsed=self.parsed_response,
            usage={"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
        )


# ==============================================================================
# 10 COMPREHENSIVE TEST CASES FOR THINKING LOOP WITH VECTOR DB
# ==============================================================================

@pytest.mark.asyncio
async def test_case_1_vector_search_triggered_via_initial_target():
    """
    Test 1: Verify when initial_search_target='vector', ThinkingLoopAgent
    executes vector search on lore_retriever instead of web search on Cycle 1.
    """
    tracker = DummyTracker()
    embedder = DummyEmbedder()
    lore_retriever = DummyLoreRetriever()
    web_tool = AsyncMock()

    agent = ThinkingLoopAgent(pipeline_tracker=tracker, lore_retriever=lore_retriever)

    context, steps = await agent.run(
        session=None,
        user_id="user_123",
        user_message="kỹ năng của Chisa là gì",
        history=[],
        initial_context="Initial incomplete context",
        llm=DummyLLM(),
        embedder=embedder,
        web_search_tool=web_tool,
        initial_search_query="kỹ năng Kuchiba Chisa",
        initial_extracted_facts="Chisa là trợ lý AI",
        initial_search_target="vector",
    )

    assert len(lore_retriever.calls) == 3  # 3 collections: character_lore, world_lore, story_lore
    assert len(embedder.calls) == 1
    assert embedder.calls[0][1] == "query: "  # prefix used
    assert web_tool.execute.call_count == 0  # Web search not triggered
    assert len(steps) >= 1
    assert steps[0]["search_target"] == "vector"
    assert "[LORE" in context


@pytest.mark.asyncio
async def test_case_2_multi_collection_vector_search_queries_all_three_stores():
    """
    Test 2: Verify vector search in Loop Thinking queries all 3 Qdrant collections
    ('character_lore', 'world_lore', 'story_lore').
    """
    tracker = DummyTracker()
    embedder = DummyEmbedder()
    lore_retriever = DummyLoreRetriever()
    agent = ThinkingLoopAgent(pipeline_tracker=tracker, lore_retriever=lore_retriever)

    res_text, details = await agent._execute_adaptive_search(
        search_target="vector",
        search_query="vũ khí của Chisa",
        session=None,
        user_id="u1",
        llm=DummyLLM(),
        embedder=embedder,
        web_search_tool=None,
        history=[],
        lore_retriever=lore_retriever,
    )

    queried_collections = [c["collection"] for c in lore_retriever.calls]
    assert queried_collections == ["character_lore", "world_lore", "story_lore"]
    assert len(details["vector_results"]) == 3
    assert details["status"] == "success"


@pytest.mark.asyncio
async def test_case_3_vector_search_result_formatting_tuples():
    """
    Test 3: Verify 2-tuple (text, score) and 3-tuple (text, score, meta) from Qdrant
    are formatted properly with score and collection name.
    """
    tracker = DummyTracker()
    embedder = DummyEmbedder()
    multi_format_data = {
        "character_lore": [("Skill A: Hồi phục năng lượng", 0.92, {"id": "c1"})],
        "world_lore": [("Vùng đất Solaris-3", 0.78)],
        "story_lore": ["Cốt truyện chương 1"]
    }
    lore_retriever = DummyLoreRetriever(return_data=multi_format_data)
    agent = ThinkingLoopAgent(pipeline_tracker=tracker, lore_retriever=lore_retriever)

    res_text, details = await agent._execute_adaptive_search(
        search_target="vector",
        search_query="kỹ năng và thế giới",
        session=None,
        user_id="u1",
        llm=DummyLLM(),
        embedder=embedder,
        web_search_tool=None,
        history=[],
        lore_retriever=lore_retriever,
    )

    assert "[LORE (character_lore)] (score=0.92):" in res_text
    assert "Skill A: Hồi phục năng lượng" in res_text
    assert "[LORE (world_lore)] (score=0.78):" in res_text
    assert "Vùng đất Solaris-3" in res_text
    assert len(details["vector_results"]) == 3


@pytest.mark.asyncio
async def test_case_4_auto_satisfy_on_cycle_1_vector_hit():
    """
    Test 4: Verify auto-satisfy triggers immediately when Cycle 1 vector search returns >= 1 hit,
    bypassing Cycle 2 LLM call to save latency.
    """
    tracker = DummyTracker()
    embedder = DummyEmbedder()
    lore_retriever = DummyLoreRetriever(return_data=[("Lore text found", 0.88, {})])
    llm = DummyLLM()
    agent = ThinkingLoopAgent(pipeline_tracker=tracker, lore_retriever=lore_retriever)

    context, steps = await agent.run(
        session=None,
        user_id="u1",
        user_message="thông tin Chisa",
        history=[],
        initial_context="some context",
        llm=llm,
        embedder=embedder,
        web_search_tool=None,
        initial_search_query="thông tin Chisa",
        initial_search_target="vector",
    )

    # Check that auto-satisfy step was emitted in tracker
    auto_satisfy_steps = [s for s in tracker.steps if s["name"] == "thinking_loop_auto_satisfy"]
    assert len(auto_satisfy_steps) == 1
    assert auto_satisfy_steps[0]["data"]["auto_satisfied"] is True
    assert auto_satisfy_steps[0]["data"]["search_target"] == "vector"
    assert auto_satisfy_steps[0]["data"]["vector_count"] >= 1
    assert len(llm.calls) == 0  # LLM Cycle 2 was bypassed!


@pytest.mark.asyncio
async def test_case_5_vector_search_cycle_2_continuation_when_cycle_1_misses():
    """
    Test 5: Verify when Cycle 1 vector search returns 0 hits, loop proceeds to Cycle 2
    where LLM synthesizes refined vector query.
    """
    tracker = DummyTracker()
    embedder = DummyEmbedder()
    # Cycle 1 returns empty list, Cycle 2 returns valid hit
    call_count = {"val": 0}

    class DynamicLoreRetriever:
        async def retrieve_lore_parent_child(self, collection, query_vector, **kwargs):
            call_count["val"] += 1
            if call_count["val"] <= 3:  # 3 collections for Cycle 1
                return []
            return [("Chisa Ultimate Skill: Blossom Strike", 0.95, {})]

    lore_retriever = DynamicLoreRetriever()
    llm_cycle_2_response = {
        "has_enough_info": False,
        "search_query": "Chisa Blossom Strike",
        "search_target": "vector",
        "distilled_facts": "Đang tìm chiêu cuối",
    }
    llm = DummyLLM(parsed_response=llm_cycle_2_response)
    agent = ThinkingLoopAgent(pipeline_tracker=tracker, lore_retriever=lore_retriever)

    context, steps = await agent.run(
        session=None,
        user_id="u1",
        user_message="chiêu cuối của Chisa là gì",
        history=[],
        initial_context="context ban đầu",
        llm=llm,
        embedder=embedder,
        web_search_tool=None,
        initial_search_query="chiêu cuối Chisa",
        initial_search_target="vector",
    )

    assert len(steps) == 2  # Executed Cycle 1 then Cycle 2
    assert steps[0]["cycle"] == 1
    assert steps[1]["cycle"] == 2
    assert "Blossom Strike" in context
    assert len(llm.calls) == 1  # LLM called for Cycle 2 query synthesis


@pytest.mark.asyncio
async def test_case_6_hybrid_search_target_executes_vector_and_web():
    """
    Test 6: Verify search_target='both' concurrently executes Vector Lore retrieval AND Web Search.
    """
    tracker = DummyTracker()
    embedder = DummyEmbedder()
    lore_retriever = DummyLoreRetriever(return_data=[("Lore: Chisa là ai", 0.80, {})])
    web_tool = AsyncMock()
    web_tool.execute.return_value = {
        "message": "Web search: Wuthering Waves update news",
        "snippets": [{"title": "News", "link": "http://test.com", "snippet": "Chisa update news..."}],
        "status": "success",
        "provider": "duckduckgo",
    }

    agent = ThinkingLoopAgent(pipeline_tracker=tracker, lore_retriever=lore_retriever)

    res_text, details = await agent._execute_adaptive_search(
        search_target="both",
        search_query="Chisa release date and lore",
        session=None,
        user_id="u1",
        llm=DummyLLM(),
        embedder=embedder,
        web_search_tool=web_tool,
        history=[],
        lore_retriever=lore_retriever,
    )

    assert "[LORE" in res_text
    assert "[WEB SEARCH]:" in res_text
    assert len(details["vector_results"]) > 0
    assert len(details["snippets"]) > 0
    assert web_tool.execute.call_count == 1


@pytest.mark.asyncio
async def test_case_7_context_accumulation_preserves_facts_and_vector_chunks():
    """
    Test 7: Verify accumulated context retains distilled facts, thinking reasoning, and lore chunks.
    """
    tracker = DummyTracker()
    embedder = DummyEmbedder()
    lore_retriever = DummyLoreRetriever(return_data=[("Resonance Liberation: 500% damage", 0.91, {})])
    agent = ThinkingLoopAgent(pipeline_tracker=tracker, lore_retriever=lore_retriever)

    context, steps = await agent.run(
        session=None,
        user_id="u1",
        user_message="sát thương chiêu cuối",
        history=[{"role": "user", "content": "hello"}],
        initial_context="[Initial Facts]: Chisa hệ Havoc",
        llm=DummyLLM(),
        embedder=embedder,
        web_search_tool=None,
        initial_search_query="sát thương Resonance Liberation Chisa",
        initial_extracted_facts="Chisa hệ Havoc",
        initial_search_target="vector",
    )

    assert "[Initial Facts]: Chisa hệ Havoc" in context
    assert "[Thinking Cycle 1 (VECTOR) Reasoning]:" in context
    assert "Resonance Liberation: 500% damage" in context


@pytest.mark.asyncio
async def test_case_8_end_to_end_rag_pipeline_vector_loop_tool_output_assembly():
    """
    Test 8: Verify end-to-end RAGPipeline integrates Vector Loop output into tool_output_msg
    with [SEARCH DATA — FACTUAL SUMMARY] and [SEARCH DATA — LATEST RETRIEVED DETAILS].
    """
    tracker = DummyTracker()
    embedder = DummyEmbedder()
    lore_retriever = DummyLoreRetriever(return_data=[("Lore: Skill Forte Circuit details", 0.89, {})])

    class UnalignedLoreAssessor:
        async def assess_alignment(self, user_message, context_text, llm, *args, **kwargs):
            return False, "Thiếu thông tin Forte Circuit", "Forte Circuit Chisa", True, "Chisa dùng súng"

    thinking_loop = ThinkingLoopAgent(pipeline_tracker=tracker, lore_retriever=lore_retriever)

    pipeline = RAGPipeline(
        memory_retriever=AsyncMock(retrieve_memories=AsyncMock(return_data=[])),
        lore_retriever=lore_retriever,
        assessor=UnalignedLoreAssessor(),
        thinking_loop_agent=thinking_loop,
        pipeline_tracker=tracker,
    )

    context = await pipeline.retrieve_and_align(
        session=None,
        user_id="u1",
        user_message="cho anh hỏi cơ chế Forte Circuit của Chisa",
        query_vector=[0.1, 0.2, 0.3],
        cleaned_query="co che forte circuit chisa",
        intents=["LORE"],
        current_emotions={},
        history=[],
        llm=DummyLLM(),
        embedder=embedder,
        web_search_tool=None,
        is_small_talk=False,
        needs_vector_search=True,
    )

    assert context.tool_output_msg != ""
    assert "[SEARCH DATA — FACTUAL SUMMARY]:" in context.tool_output_msg
    assert "Chisa dùng súng" in context.tool_output_msg
    assert "[SEARCH DATA — LATEST RETRIEVED DETAILS]:" in context.tool_output_msg
    assert "Forte Circuit details" in context.tool_output_msg


@pytest.mark.asyncio
async def test_case_9_vector_search_exception_resiliency():
    """
    Test 9: Verify when lore_retriever raises an unhandled exception, ThinkingLoopAgent
    catches it gracefully without crashing and returns valid context.
    """
    tracker = DummyTracker()
    embedder = DummyEmbedder()

    class FailingLoreRetriever:
        async def retrieve_lore_parent_child(self, **kwargs):
            raise ConnectionError("Qdrant database connection timeout")

    lore_retriever = FailingLoreRetriever()
    agent = ThinkingLoopAgent(pipeline_tracker=tracker, lore_retriever=lore_retriever)

    res_text, details = await agent._execute_adaptive_search(
        search_target="vector",
        search_query="test query",
        session=None,
        user_id="u1",
        llm=DummyLLM(),
        embedder=embedder,
        web_search_tool=None,
        history=[],
        lore_retriever=lore_retriever,
    )

    assert res_text == "No search results returned."
    assert details["vector_results"] == []


@pytest.mark.asyncio
async def test_case_10_score_threshold_filtering_filters_low_confidence_chunks():
    """
    Test 10: Verify score_threshold=0.30 is passed to retrieve_lore_parent_child
    to filter out low-confidence vector noise.
    """
    tracker = DummyTracker()
    embedder = DummyEmbedder()
    lore_retriever = DummyLoreRetriever()
    agent = ThinkingLoopAgent(pipeline_tracker=tracker, lore_retriever=lore_retriever)

    await agent._execute_adaptive_search(
        search_target="vector",
        search_query="vũ khí",
        session=None,
        user_id="u1",
        llm=DummyLLM(),
        embedder=embedder,
        web_search_tool=None,
        history=[],
        lore_retriever=lore_retriever,
    )

    for call in lore_retriever.calls:
        assert call["score_threshold"] == 0.30
        assert call["top_k"] == 3


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main(["-v", __file__]))

