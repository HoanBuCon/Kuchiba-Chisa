import pytest
from app.domain.services.semantic_router import SemanticRouter, ROUTER_ANCHORS
from app.domain.services.intent_classifier import ChatIntent

class MockEmbedder:
    async def embed_text(self, text: str) -> list[float]:
        # Trả về các unit vector đơn giản để so sánh độ tương đồng cosine
        text_lower = text.lower()
        
        # Kiểm tra sự xuất hiện trong anchors
        for intent, anchor_tuples in ROUTER_ANCHORS.items():
            for anchor, _ in anchor_tuples:
                if anchor in text_lower or text_lower in anchor:
                    if intent == ChatIntent.CHARACTER_LORE:
                        return [1.0, 0.0, 0.0, 0.0, 0.0]
                    elif intent == ChatIntent.WORLD_LORE:
                        return [0.0, 1.0, 0.0, 0.0, 0.0]
                    elif intent == ChatIntent.STORY_LORE:
                        return [0.0, 0.0, 1.0, 0.0, 0.0]
                    elif intent == ChatIntent.MEMORY:
                        return [0.0, 0.0, 0.0, 1.0, 0.0]
                    elif intent == ChatIntent.SYSTEM_ACTION:
                        return [0.0, 0.0, 0.0, 0.0, 1.0]
                    
        return [0.0, 0.0, 0.0, 0.0, 0.0]


@pytest.mark.asyncio
async def test_semantic_router_classification():
    embedder = MockEmbedder()
    router = SemanticRouter(embedder=embedder, threshold=0.7)
    
    # Khởi tạo ma trận anchors
    await router.initialize()
    
    # 1. Test CHARACTER_LORE
    intents = await router.classify("vũ khí của em là gì")
    assert ChatIntent.CHARACTER_LORE in intents
    assert ChatIntent.WORLD_LORE not in intents

    # 2. Test WORLD_LORE
    intents = await router.classify("sonoro sphere là gì")
    assert ChatIntent.WORLD_LORE in intents

    # 3. Test SYSTEM_ACTION
    intents = await router.classify("tóm tắt lại nội dung cuộc trò chuyện nãy giờ giúp anh")
    assert ChatIntent.SYSTEM_ACTION in intents
    
    intents_search = await router.classify("tra mạng giúp anh tin tức này")
    assert ChatIntent.SYSTEM_ACTION in intents_search

    # 4. Test không khớp (không vượt ngưỡng threshold)
    intents = await router.classify("hôm nay ăn gì nhỉ")
    assert len(intents) == 0


@pytest.mark.asyncio
async def test_semantic_router_avoids_character_false_positive():
    embedder = MockEmbedder()
    router = SemanticRouter(embedder=embedder, threshold=0.7)
    await router.initialize()

    intents = await router.classify("game có vũ khí không")
    assert ChatIntent.CHARACTER_LORE not in intents


@pytest.mark.asyncio
async def test_semantic_router_ambiguous_message_returns_no_intent():
    embedder = MockEmbedder()
    router = SemanticRouter(embedder=embedder, threshold=0.7)
    await router.initialize()

    intents = await router.classify("em có biết gì về vũ khí")
    assert len(intents) == 0
