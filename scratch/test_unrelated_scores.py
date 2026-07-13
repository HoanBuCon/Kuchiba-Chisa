import sys
import os
sys.path.append(os.getcwd())

import asyncio
from app.infrastructure.embeddings.fastembed_adapter import FastEmbedAdapter
from app.infrastructure.vector.qdrant.qdrant_service import qdrant_service

async def main():
    # Reconfigure stdout to use UTF-8 on Windows
    if sys.stdout.encoding != 'utf-8':
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except Exception:
            pass

    embedder = FastEmbedAdapter()
    query = "Tập đoàn nào thuộc quân đội nhân dân Việt Nam nhưng lại sản xuất và gia công phần mềm vậy em"
    vec = await embedder.embed_text(query)
    results = await qdrant_service.search_lore(
        collection="character_lore",
        query_vector=vec,
        limit=5,
        score_threshold=0.0
    )
    print("Scores for unrelated query:")
    for r in results:
        text = r['payload'].get('text_content', '')
        # Only print ASCII characters to be completely safe from encoding issues
        safe_text = text.encode('ascii', errors='ignore').decode('ascii')[:60]
        print(f"Score: {r['score']:.4f} | Content: {safe_text}...")

if __name__ == "__main__":
    asyncio.run(main())
