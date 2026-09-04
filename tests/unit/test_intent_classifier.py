import pytest

from app.domain.services.intent_classifier import ChatIntent, IntentClassifier


class DummyLLM:
    pass


class DummyEmbedder:
    def __init__(self):
        self.calls = 0

    async def embed_text(self, text: str, prefix: str = "query") -> list[float]:
        self.calls += 1
        return [0.0, 0.0, 0.0]


class FailSemanticRouter:
    async def classify(self, user_message: str, query_vector=None):
        raise AssertionError("Semantic router should not run for fast-path cases")


@pytest.mark.asyncio
async def test_small_talk_bypass_returns_small_talk_without_embedding():
    classifier = IntentClassifier(llm=DummyLLM(), embedder=DummyEmbedder())

    intents, _ = await classifier.classify("hihi")

    assert intents == [ChatIntent.SMALL_TALK]
    assert classifier.embedder.calls == 0


@pytest.mark.asyncio
async def test_ambiguous_personal_question_uses_knowledge_gateway():
    classifier = IntentClassifier(llm=DummyLLM(), embedder=DummyEmbedder())

    intents, _ = await classifier.classify("tên anh là gì")

    assert intents == [ChatIntent.KNOWLEDGE_OR_TASK]


@pytest.mark.asyncio
async def test_character_false_positive_prevented_by_boundary_regex():
    classifier = IntentClassifier(llm=DummyLLM(), embedder=DummyEmbedder())

    intents, _ = await classifier.classify("game có vũ khí không", query_vector=[0.0, 0.0, 0.0])

    assert ChatIntent.LORE not in intents


@pytest.mark.asyncio
async def test_conversation_summary_request_uses_knowledge_gateway():
    classifier = IntentClassifier(llm=DummyLLM(), embedder=DummyEmbedder())

    intents, _ = await classifier.classify("tóm tắt cuộc trò chuyện nãy giờ")

    assert intents == [ChatIntent.KNOWLEDGE_OR_TASK]
