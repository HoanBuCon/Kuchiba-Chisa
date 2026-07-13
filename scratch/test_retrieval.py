import asyncio
import os
import sys

sys.path.append(os.getcwd())

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from app.infrastructure.embeddings.fastembed_adapter import FastEmbedAdapter
from app.infrastructure.vector.qdrant.qdrant_service import qdrant_service
from app.domain.services.rag.retriever_lore import LoreRetriever
from app.domain.services.rag.reranker import KeywordOverlapReranker

async def main():
    query_text = "em học trường nào vậy"
    print(f"Query: '{query_text}'")
    
    embedder = FastEmbedAdapter()
    query_vector = await embedder.embed_text(query_text)
    
    # Simulate retrieve_lore_parent_child with limit=40 and threshold=0.30
    candidates = await qdrant_service.search_lore(
        collection="character_lore",
        query_vector=query_vector,
        limit=40,
        score_threshold=0.30,
    )
    
    print(f"\nCandidates retrieved from Qdrant (limit=40, threshold=0.30): {len(candidates)}")
    
    # Apply keyword reranking
    reranker = KeywordOverlapReranker()
    query_tokens = reranker.tokenize(query_text)
    print(f"Query tokens: {query_tokens}")
    
    scored_candidates = []
    for cand in candidates:
        payload = cand.get("payload", {})
        child_text = payload.get("text_content", "")
        score = cand.get("score", 0.0)
        if child_text:
            keyword_score = reranker.calculate_score(query_tokens, child_text)
            hybrid_score = (score * 0.75) + (keyword_score * 0.25)
            
            # Find matching tokens in child_text
            child_lower = child_text.lower()
            matching_tokens = [t for t in query_tokens if t in child_lower]
            
            scored_candidates.append({
                "child_text": child_text,
                "parent_title": payload.get("section", ""),
                "parent_full_text": payload.get("parent_full_text", ""),
                "parent_id": payload.get("parent_id"),
                "vector_score": score,
                "keyword_score": keyword_score,
                "hybrid_score": hybrid_score,
                "matching_tokens": matching_tokens
            })
            
    scored_candidates.sort(key=lambda x: x["hybrid_score"], reverse=True)
    
    print("\n--- Top Scored & Reranked candidates ---")
    for i, item in enumerate(scored_candidates[:15]):
        print(f"{i+1}. Hybrid: {item['hybrid_score']:.4f} | Vec: {item['vector_score']:.4f} | Key: {item['keyword_score']:.4f} | Parent: [{item['parent_title']}] | Matching tokens: {item['matching_tokens']}")
        print(f"   Child text: {item['child_text'][:120]}...")

    # Parent-child deduplication logic as in LoreRetriever
    seen_parents = set()
    lore_chunks = []
    print("\n--- Final parent chunks selected (deduplicated) ---")
    for item in scored_candidates:
        parent_id = item["parent_id"]
        parent_text = item["parent_full_text"] or item["child_text"]
        parent_title = item["parent_title"]
        if parent_id:
            if parent_id not in seen_parents:
                seen_parents.add(parent_id)
                lore_chunks.append((parent_title, parent_text))
        else:
            lore_chunks.append((parent_title, parent_text))
            
    for i, (title, text) in enumerate(lore_chunks[:5]):
        print(f"{i+1}. Parent Title: [{title}]")

if __name__ == "__main__":
    asyncio.run(main())
