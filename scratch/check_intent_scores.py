import sys
import os
import asyncio
sys.path.append(os.getcwd())

# Force UTF-8 encoding
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from app.infrastructure.embeddings.fastembed_adapter import FastEmbedAdapter
from app.domain.services.production_pipeline.semantic_router import SemanticRouter
import numpy as np

async def test_scores():
    embedder = FastEmbedAdapter()
    router = SemanticRouter(embedder=embedder)
    await router.initialize()
    
    test_queries = [
        "Em học ở học viện nào thế?",
        "Em sử dụng vũ khí gì?",
        "Anh cho em ăn ớt cay nhé?",
        "khi nào game cập nhật phiên bản mới"
    ]
    
    for q in test_queries:
        print(f"\nQuery: '{q}'")
        q_vec = np.array(await embedder.embed_text(q))
        for intent, anchor_matrix in router.route_embeddings.items():
            similarities = router._cosine_similarity(q_vec, anchor_matrix)
            max_sim = float(np.max(similarities))
            print(f"  - {intent.value}: {max_sim:.4f}")

if __name__ == "__main__":
    asyncio.run(test_scores())
