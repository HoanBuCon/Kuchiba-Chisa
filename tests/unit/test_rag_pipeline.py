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
    async def assess_alignment(self, user_message, context_text, llm):
        return True, "aligned", ""


class DummyThinkingLoop:
    async def run(self, **kwargs):
        return "", []


@pytest.mark.asyncio
async def test_no_retrieval_for_other_and_system_action_intents():
    memory_retriever = DummyMemoryRetriever()
    lore_retriever = DummyLoreRetriever()
    pipeline = RAGPipeline(
        memory_retriever=memory_retriever,
        lore_retriever=lore_retriever,
        assessor=DummyAssessor(),
        thinking_loop_agent=DummyThinkingLoop(),
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
