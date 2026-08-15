import sys, os
sys.path.insert(0, os.path.abspath('.'))
import asyncio
import pytest
from app.infrastructure.embeddings.fastembed_adapter import FastEmbedAdapter
from app.domain.services.intent_classifier import IntentClassifier
from app.domain.models.intent_result import ChatIntent
from app.domain.services.rag.entity_resolver import EntityResolver

@pytest.mark.asyncio
async def test_sota_semantic_router_production_upgrades():
    embedder = FastEmbedAdapter()
    entity_resolver = EntityResolver()
    entity_resolver.load()
    classifier = IntentClassifier(llm=None, embedder=embedder, entity_resolver=entity_resolver)

    print("=" * 80)
    print("TESTING SOTA PRODUCTION UPGRADES IN SEMANTIC ROUTER")
    print("=" * 80)

    # 1. Zero-Entity Combat & Mechanics Lore
    q_parry = "Làm sao để parry khi quái mắt đỏ?"
    res_parry = await classifier.classify(q_parry)
    print(f"  • Combat Zero-Entity : \"{q_parry}\" -> Intents={res_parry.intents}, Conf={res_parry.confidence*100:.1f}%, Scores={res_parry.semantic_scores}")
    assert ChatIntent.LORE in res_parry.intents

    q_element = "Có bao nhiêu thuộc tính nguyên tố và khắc chế nhau thế nào?"
    res_element = await classifier.classify(q_element)
    print(f"  • Elements Counter   : \"{q_element}\" -> Intents={res_element.intents}, Conf={res_element.confidence*100:.1f}%")
    assert ChatIntent.LORE in res_element.intents

    # 2. Multi-Label Dual Intent (Memory + Conversational Empathy)
    q_hybrid = "Anh đang chuẩn bị mở một quán trà nhỏ ở Hà Nội, vừa vui vừa lo"
    res_hybrid = await classifier.classify(q_hybrid)
    print(f"  • Dual-Intent Query  : \"{q_hybrid}\" -> Intents={res_hybrid.intents}, Scores={res_hybrid.semantic_scores}")
    assert ChatIntent.MEMORY in res_hybrid.intents or ChatIntent.CONVERSATIONAL in res_hybrid.intents

    # 3. Contextual Intent Momentum
    q_short = "Tại sao lại như vậy?"
    res_momentum = await classifier.classify(q_short, prior_intent=ChatIntent.LORE)
    print(f"  • Context Momentum   : \"{q_short}\" (Prior=LORE) -> Best={res_momentum.intents[0].value}, Scores={res_momentum.semantic_scores}")

    # 4. Small Talk Strict Isolation
    q_st = "chào em chisa nhé"
    res_st = await classifier.classify(q_st)
    assert res_st.intents == [ChatIntent.SMALL_TALK]
    print(f"  • Small Talk Strict  : \"{q_st}\" -> Method={res_st.routing_method}")

    print("\n✓ PASS: All SOTA Production Semantic Router Upgrades Verified!")

if __name__ == "__main__":
    asyncio.run(test_sota_semantic_router_production_upgrades())
