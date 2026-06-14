import asyncio
import os
import sys

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

sys.path.append(os.getcwd())

from app.infrastructure.vector.qdrant.qdrant_service import qdrant_service
from app.infrastructure.embeddings.fastembed_adapter import FastEmbedAdapter

async def test_search():
    embedder = FastEmbedAdapter()
    
    test_queries = {
        "character_lore": [
            "Chisa sử dụng vũ khí gì?",
            "Mối quan hệ giữa Chisa và Rover?",
            "Năng lực Forte của Chisa hoạt động thế nào?"
        ],
        "world_lore": [
            "Sonoro Sphere hình thành và hoạt động thế nào?",
            "Tập đoàn Spacetrek chuyên nghiên cứu cái gì?",
            "Hiện tượng Overclocking nguy hiểm thế nào?"
        ],
        "story_lore": [
            "Chisa bị mắc kẹt ở Honami bao nhiêu năm?",
            "Sumika để lại cái gì cho Chisa?",
            "Lễ hội mùa hạ ở Startorch Academy có sự kiện gì đáng nhớ?"
        ]
    }
    
    print("=" * 60)
    print(" VERIFYING HYBRID-FORMAT LORE RETRIEVAL IN QDRANT")
    print("=" * 60)
    
    for collection, queries in test_queries.items():
        print(f"\n=== Collection: {collection} ===")
        for query in queries:
            print(f"\nQuery: '{query}'")
            vector = await embedder.embed_text(query)
            
            results = await qdrant_service.search_lore(
                collection=collection,
                query_vector=vector,
                limit=3,
                score_threshold=0.3
            )
            
            if not results:
                print("   [x] No results found above threshold (0.3)")
            else:
                for idx, r in enumerate(results):
                    score = r["score"]
                    text = r["payload"].get("text_content", "")
                    print(f"   {idx+1}. Score: {score:.4f} -> {text}")

if __name__ == "__main__":
    asyncio.run(test_search())
