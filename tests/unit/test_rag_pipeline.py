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

    async def retrieve_lore_parent_child(self, **kwargs):
        self.calls += 1
        return []


class DummyAssessor:
    async def assess_alignment(self, user_message, context_text, llm, *args, **kwargs):
        return True, "aligned", "", True


class DummyThinkingLoop:
    async def run(self, **kwargs):
        return "", []


class DummyPipelineTracker:
    def add_step(self, name, data):
        pass


@pytest.mark.asyncio
async def test_no_retrieval_for_other_and_system_action_intents():
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
        intents=["OTHER", "SYSTEM_ACTION"],
        current_emotions={},
        history=[],
        llm=None,
        embedder=None,
        web_search_tool=None,
        is_small_talk=False,
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
