import pytest

from app.domain.services.rag.pipeline import RAGPipeline


class DummyMemoryRetriever:
    def __init__(self):
        self.calls = 0

    async def retrieve_memories(self, **kwargs):
        self.calls += 1
        return []


class DummyLoreRetriever:
    def __init__(self):
        self.calls = 0
        self.request_options = []

    async def retrieve_lore_parent_child(self, **kwargs):
        self.calls += 1
        self.request_options.append(kwargs)
        return []


class DummyAssessor:
    async def assess_alignment(self, user_message, context_text, llm, *args, **kwargs):
        return True, "aligned", "", True, "", "vector"


class DummyThinkingLoop:
    async def run(self, **kwargs):
        return "", []


class DummyPipelineTracker:
    def add_step(self, name, data, *args, **kwargs):
        pass



@pytest.mark.asyncio
async def test_no_retrieval_for_small_talk_and_system_action_intents():
    memory_retriever = DummyMemoryRetriever()
    lore_retriever = DummyLoreRetriever()
    pipeline = RAGPipeline(
        memory_retriever=memory_retriever,
        lore_retriever=lore_retriever,
        assessor=DummyAssessor(),
        thinking_loop_agent=DummyThinkingLoop(),
        pipeline_tracker=DummyPipelineTracker(),
    )

    context = await pipeline.retrieve_and_align(
        session=None,
        user_id="u1",
        user_message="tóm tắt giúp anh",
        query_vector=[0.1, 0.2],
        cleaned_query="tom tat",
        intents=["SMALL_TALK", "SYSTEM_ACTION"],
        current_emotions={},
        history=[],
        llm=None,
        embedder=None,
        web_search_tool=None,
        is_small_talk=False,
        needs_vector_search=False,
    )

    assert memory_retriever.calls == 0
    assert lore_retriever.calls == 0
    assert context.lore_chunks == []
    assert context.memories == []


@pytest.mark.asyncio
async def test_retrieval_runs_when_memory_intent_present():
    memory_retriever = DummyMemoryRetriever()
    lore_retriever = DummyLoreRetriever()
    pipeline = RAGPipeline(
        memory_retriever=memory_retriever,
        lore_retriever=lore_retriever,
        assessor=DummyAssessor(),
        thinking_loop_agent=DummyThinkingLoop(),
        pipeline_tracker=DummyPipelineTracker(),
    )

    await pipeline.retrieve_and_align(
        session=None,
        user_id="u1",
        user_message="em nhớ gì về anh",
        query_vector=[0.1, 0.2],
        cleaned_query="nho ve anh",
        intents=["MEMORY"],
        current_emotions={},
        history=[],
        llm=None,
        embedder=None,
        web_search_tool=None,
        is_small_talk=False,
    )

    assert memory_retriever.calls == 1
    assert lore_retriever.calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("intents", "expected_rerank"),
    [
        (["LORE"], True),
        (["KNOWLEDGE_OR_TASK"], True),
        (["OTHER"], False),
    ],
)
async def test_only_lore_or_factual_intents_enable_cross_encoder_reranking(
    intents: list[str], expected_rerank: bool
) -> None:
    lore_retriever = DummyLoreRetriever()
    pipeline = RAGPipeline(
        memory_retriever=DummyMemoryRetriever(),
        lore_retriever=lore_retriever,
        assessor=DummyAssessor(),
        thinking_loop_agent=DummyThinkingLoop(),
        pipeline_tracker=DummyPipelineTracker(),
    )

    await pipeline.retrieve_and_align(
        session=None,
        user_id="u1",
        user_message="retrieval test",
        query_vector=[0.1, 0.2],
        cleaned_query="retrieval test",
        intents=intents,
        current_emotions={},
        history=[],
        llm=None,
        embedder=None,
        web_search_tool=None,
        is_small_talk=False,
    )

    assert lore_retriever.calls == 3
    assert {
        options["enable_cross_encoder_rerank"]
        for options in lore_retriever.request_options
    } == {expected_rerank}


class DummyFalseLoreAssessor:
    async def assess_alignment(self, user_message, context_text, llm, *args, **kwargs):
        # returns is_aligned=False, reason="unaligned", search_query="test", use_lore=False
        return False, "unaligned", "test", False


@pytest.mark.asyncio
async def test_lore_chunks_filtered_out_when_use_lore_false():
    class DummyLoreRetrieverWithData:
        async def retrieve_lore_parent_child(self, **kwargs):
            return ["Some lore data"]

    pipeline = RAGPipeline(
        memory_retriever=DummyMemoryRetriever(),
        lore_retriever=DummyLoreRetrieverWithData(),
        assessor=DummyFalseLoreAssessor(),
        thinking_loop_agent=DummyThinkingLoop(),
        pipeline_tracker=DummyPipelineTracker(),
    )

    context = await pipeline.retrieve_and_align(
        session=None,
        user_id="u1",
        user_message="Tập đoàn nào thuộc quân đội nhân dân Việt Nam sản xuất phần mềm?",
        query_vector=[0.1, 0.2],
        cleaned_query="quan doi san xuat phan mem",
        intents=["LORE"],
        current_emotions={},
        history=[],
        llm=None,
        embedder=None,
        web_search_tool=None,
        is_small_talk=False,
    )

    assert context.lore_chunks == []


@pytest.mark.asyncio
async def test_web_search_snippet_quality_gate_and_ranking():
    from app.domain.services.tools.web_search import WebSearchAgentTool

    raw_snippets = [
        "Short",  # Too short (< 30)
        "Wuthering Waves version 2.8 will be released on October 15 with new 5-star character Chisa.",
        "Wuthering Waves version 2.8 will be released on October 15 with new 5-star character Chisa.",  # Exact duplicate
        "wuthering waves version 2.8 will be released on october 15 with new 5-star character chisa.",  # Fuzzy duplicate
        "Completely irrelevant text about cooking pasta with tomato sauce and mozzarella cheese.",
        "Patch notes for Wuthering Waves 2.8 highlight new Havoc resonators and combat balance.",
    ]
    query = "Wuthering Waves 2.8 release date Chisa"

    filtered = WebSearchAgentTool._filter_quality_snippets(raw_snippets, query)
    assert len(filtered) == 2
    assert "October 15" in filtered[0]
    assert "Patch notes" in filtered[1]

    # Test Smart URL Ranking
    raw_urls = [
        "https://www.youtube.com/watch?v=12345",  # Blacklisted
        "https://randomblog.com/news/123",
        "https://wutheringwaves.wiki/Chisa",  # Boosted domain + keyword
        "https://en.wikipedia.org/wiki/Wuthering_Waves",  # Boosted domain
    ]
    ranked = WebSearchAgentTool._rank_urls_by_relevance(raw_urls, filtered, query)
    assert len(ranked) == 3
    assert "youtube.com" not in [u.lower() for u in ranked]
    assert "wutheringwaves.wiki" in ranked[0] or "wikipedia.org" in ranked[0]


@pytest.mark.asyncio
async def test_context_assessor_distillation_formats():
    from app.domain.interfaces.llm_provider import BaseLLMAdapter, LLMResponse, StructuredPrompt
    from app.domain.services.rag.assessor import ContextAssessor

    class MockAssessorLLM(BaseLLMAdapter):
        def __init__(self, raw_facts):
            self.raw_facts = raw_facts

        async def generate(self, prompt: StructuredPrompt) -> LLMResponse:
            return LLMResponse(
                raw_content="{}",
                parsed={
                    "is_aligned": True,
                    "reason": "Sufficient context",
                    "extracted_facts": self.raw_facts,
                    "use_lore": True
                },
                input_tokens=100,
                output_tokens=50,
                model="mock"
            )

        async def stream(self, prompt): yield ""
        async def validate_response(self, raw, schema): return {}
        async def estimate_tokens(self, text): return len(text.split())

    assessor = ContextAssessor()

    # Case 1: List format
    llm_list = MockAssessorLLM(["Chisa birthday is October 15", "Element is Havoc"])
    is_aligned, reason, query, use_lore, facts, search_target = await assessor.assess_alignment(
        "Chisa", "lore", llm_list
    )
    assert is_aligned is True
    assert search_target == "web"
    assert "- Chisa birthday is October 15" in facts
    assert "- Element is Havoc" in facts

    # Case 2: String format
    llm_str = MockAssessorLLM("Chisa uses Havoc katana.\nBase ATK is 587 at level 90.")
    _, _, _, _, facts_str, _ = await assessor.assess_alignment("Chisa", "lore", llm_str)
    assert "- Chisa uses Havoc katana." in facts_str
    assert "- Base ATK is 587 at level 90." in facts_str


@pytest.mark.asyncio
async def test_windowed_parent_resolution():
    from app.domain.services.rag.retriever_lore import LoreRetriever

    # Large parent markdown (~2000 chars)
    parent_md = (
        "# Kuchiba Chisa Section 1\n"
        + "Introductory text about the world of Solaris-3 and Lament disaster. " * 15
        + "\n\n## Combat Attributes\n"
        + "Chisa wields a Havoc blade with resonance skill Shadow Step dealing 450% Havoc damage. "
        + "Her ultimate skill activates Dark Domain for 12 seconds with 25% crit rate buff.\n\n"
        + "Additional lore background about Midnight Rangers and general Jiyan. " * 15
    )
    child_text = "Chisa wields a Havoc blade with resonance skill Shadow Step dealing 450% Havoc damage."

    windowed = LoreRetriever.resolve_windowed_parent(parent_md, child_text, window_chars=500)
    assert len(windowed) <= 800
    assert child_text in windowed
    assert "..." in windowed


@pytest.mark.asyncio
async def test_thinking_loop_adaptive_search_and_auto_satisfy():
    from app.domain.services.rag.thinking_loop import ThinkingLoopAgent

    class MockWebTool:
        async def execute(self, **kwargs):
            return {
                "status": "success",
                "message": "Found 2.8 update on Oct 15",
                "snippets": ["Snippet 1: Oct 15 release", "Snippet 2: Chisa debut"],
                "provider": "mock"
            }

    tracker = DummyPipelineTracker()
    agent = ThinkingLoopAgent(pipeline_tracker=tracker)

    # Test auto-satisfy on Cycle 1 with initial search query
    ctx, steps = await agent.run(
        session=None,
        user_id="u1",
        user_message="When is 2.8?",
        history=[],
        initial_context="",
        llm=None,
        embedder=None,
        web_search_tool=MockWebTool(),
        initial_search_query="Wuthering Waves 2.8 update date",
        initial_search_target="web",
    )

    assert len(steps) == 1
    assert steps[0]["cycle"] == 1
    assert "Found 2.8 update" in ctx


@pytest.mark.asyncio
async def test_context_builder_attention_layout_and_u_curve():
    from app.domain.entities.emotion import EmotionState
    from app.domain.services.budget_mode import BudgetMode
    from app.domain.services.context_builder import ContextBuilder

    # Test U-curve sorting: 1st best at start, 2nd best at end, lower scores in middle
    items = ["1st_best", "2nd_best", "3rd_best", "4th_best"]
    u_sorted = ContextBuilder._u_curve_sort(items)
    assert u_sorted[0] == "1st_best"
    assert u_sorted[-1] == "2nd_best"
    assert u_sorted == ["1st_best", "3rd_best", "4th_best", "2nd_best"]

    # Test Context Builder placing OUTPUT FORMAT at bottom
    import uuid
    cb = ContextBuilder()
    emotion = EmotionState(user_id=uuid.uuid4(), joy=0.5)
    res = cb.build(
        emotion=emotion,
        attachment_bonus=0.1,
        memories=["Memory 1"],
        lore=["Lore chunk 1", "Lore chunk 2"],
        history=[],
        user_message="Tell me about Chisa lore",
        intent_name="LORE",
        tool_result="[SEARCH DATA]: Result",
        budget_mode=BudgetMode.RAG,
    )

    system_prompt = res.prompt.system
    assert "[OUTPUT FORMAT]" in system_prompt
    format_idx = system_prompt.rfind("[OUTPUT FORMAT]")
    lore_idx = system_prompt.find("[LORE — REFERENCE DATA START]")
    assert lore_idx < format_idx

