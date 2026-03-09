import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.domain.services.rag_retriever import RAGRetriever
from app.infrastructure.vector.qdrant.qdrant_service import QdrantService
from app.infrastructure.embeddings.fastembed_adapter import FastEmbedAdapter

async def test_recall():
    embedder = FastEmbedAdapter()
    qdrant = QdrantService()
    rag = RAGRetriever()

    query = "Kỉ niệm nào khiến em cảm thấy buồn nhất ?"
    vector = await embedder.embed_text(query)
    with open("scripts/recall_output.txt", "w", encoding="utf-8") as f:
        f.write(f"Querying lore for: '{query}'\n")
        lore_chunks = await rag.retrieve_lore(vector, top_k=6)
        for i, chunk in enumerate(lore_chunks):
            f.write(f"--- Chunk {i+1} ---\n{chunk}\n")

if __name__ == "__main__":
    asyncio.run(test_recall())
