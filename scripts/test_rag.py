import asyncio
import sys
import os

sys.path.append(os.getcwd())

from app.infrastructure.vector.qdrant.qdrant_service import qdrant_service
from app.infrastructure.embeddings.fastembed_adapter import FastEmbedAdapter
from app.domain.services.rag_retriever import rag_retriever

async def test_search():
    embedder = FastEmbedAdapter()
    query = "Em là Resonator hệ gì ?"
    with open("debug_rag.txt", "w", encoding="utf-8") as f:
        f.write(f"Query: {query}\n")
        
        vector = await embedder.embed_text(query)
        
        # Test qdrant directly
        results = await qdrant_service.search_lore(
            collection="chisa_lore",
            query_vector=vector,
            limit=8,
            score_threshold=0.0
        )
        
        f.write("\n--- Raw Qdrant Results ---\n")
        for idx, r in enumerate(results):
            f.write(f"{idx+1}. Score: {r['score']:.4f}\n")
            f.write(f"   Text: {r['payload'].get('text_content', '')}\n")
            
        f.write("\n--- Rag Retriever Results ---\n")
        try:
            chunks = await rag_retriever.retrieve_lore(
                query_vector=vector,
                top_k=8
            )
            for idx, chunk in enumerate(chunks):
                f.write(f"{idx+1}. {chunk}\n")
        except Exception as e:
            f.write(f"rag_retriever failed: {e}\n")

if __name__ == "__main__":
    asyncio.run(test_search())
