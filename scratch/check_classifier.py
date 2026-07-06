import sys
import os
import asyncio
sys.path.append(os.getcwd())

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from app.infrastructure.embeddings.fastembed_adapter import FastEmbedAdapter
from app.domain.services.production_pipeline.intent_classifier import IntentClassifier
from app.shared.utils.query_cleaner import clean_query_for_rag

async def test_classifier():
    embedder = FastEmbedAdapter()
    classifier = IntentClassifier(llm=None, embedder=embedder)
    await classifier.semantic_router.initialize()
    
    q = "Em học ở học viện nào thế?"
    cleaned_query = clean_query_for_rag(q)
    query_vector = await embedder.embed_text(cleaned_query)
    
    intents = await classifier.classify(q, query_vector)
    print(f"\nQuery: '{q}' (Cleaned: '{cleaned_query}')")
    print(f"Intents: {[i.value for i in intents]}")
    
    # print scores
    q_vec = classifier.semantic_router.route_embeddings
    import numpy as np
    q_v = np.array(query_vector)
    for intent, anchor_matrix in classifier.semantic_router.route_embeddings.items():
        sims = classifier.semantic_router._cosine_similarity(q_v, anchor_matrix)
        print(f"  - {intent.value}: max sim = {float(np.max(sims)):.4f}")

if __name__ == "__main__":
    asyncio.run(test_classifier())
