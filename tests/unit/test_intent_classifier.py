import pytest

from app.domain.services.intent_classifier import ChatIntent, IntentClassifier


class DummyLLM:
    pass


class DummyEmbedder:
    def __init__(self):
        self.calls = 0

    async def embed_text(self, text: str) -> list[float]:
        self.calls += 1
        return [0.0, 0.0, 0.0]


class FailSemanticRouter:
    async def classify(self, user_message: str, query_vector=None):
        raise AssertionError("Semantic router should not run for fast-path cases")


@pytest.mark.asyncio
async def test_small_talk_bypass_returns_other_without_semantic():
    classifier = IntentClassifier(llm=DummyLLM(), embedder=DummyEmbedder())
    classifier.semantic_router = FailSemanticRouter()

    intents, _ = await classifier.classify("hihi")

    assert intents == [ChatIntent.OTHER]


@pytest.mark.asyncio
async def test_memory_keyword_fast_path_without_semantic():
    classifier = IntentClassifier(llm=DummyLLM(), embedder=DummyEmbedder())
    classifier.semantic_router = FailSemanticRouter()

    intents, _ = await classifier.classify("tên anh là gì")

    assert ChatIntent.MEMORY in intents


@pytest.mark.asyncio
async def test_character_false_positive_prevented_by_boundary_regex():
    classifier = IntentClassifier(llm=DummyLLM(), embedder=DummyEmbedder())

    intents, _ = await classifier.classify("game có vũ khí không", query_vector=[0.0, 0.0, 0.0])

    assert ChatIntent.LORE not in intents


@pytest.mark.asyncio
async def test_system_action_fast_path_without_semantic():
    classifier = IntentClassifier(llm=DummyLLM(), embedder=DummyEmbedder())
    classifier.semantic_router = FailSemanticRouter()

    intents, _ = await classifier.classify("tóm tắt cuộc trò chuyện nãy giờ")

    assert ChatIntent.SYSTEM_ACTION in intents
