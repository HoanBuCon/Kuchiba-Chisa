from typing import List, Tuple, Optional
from app.domain.interfaces.vector_store import IVectorStore
from app.domain.services.rag.reranker import KeywordOverlapReranker
from app.infrastructure.logging.logger import get_logger

log = get_logger(__name__)

from app.domain.interfaces.retriever import ILoreRetriever

class LoreRetriever(ILoreRetriever):
    """
    Retrieves Chisa lore chunks from Qdrant using vector search,
    boosted by keyword overlap re-ranking.
    """
    def __init__(self, reranker: Optional[KeywordOverlapReranker] = None):
        self.reranker = reranker or KeywordOverlapReranker()

    async def retrieve_lore_standard(
        self,
        vector_store: IVectorStore,
        query_vector: List[float],
        query_text: str = "",
        top_k: int = 8,
        score_threshold: float = 0.3,
    ) -> List[Tuple[str, float]]:
        try:
            if not vector_store:
                return []
            
            candidates = await vector_store.search_lore(
                collection="persona_embeddings",
                query_vector=query_vector,
                limit=top_k,
                score_threshold=score_threshold,
            )
        except Exception as e:
            log.warning("Standard lore retrieval failed, skipping", error=str(e))
            return []

        query_tokens = self.reranker.tokenize(query_text)
        results = []
        for cand in candidates:
            text = cand.get("payload", {}).get("text_content", "")
            score = cand.get("score", 0.0)
            if text:
                keyword_score = self.reranker.calculate_score(query_tokens, text)
                hybrid_score = (score * 0.75) + (keyword_score * 0.25)
                results.append((text, hybrid_score))

        results.sort(key=lambda item: item[1], reverse=True)
        return results

    async def retrieve_lore_parent_child(
        self,
        vector_store: IVectorStore,
        collection: str,
        query_vector: List[float],
        query_text: str = "",
        top_k: int = 5,
        score_threshold: float = 0.35,
    ) -> List[str]:
        try:
            if not vector_store:
                return []
                
            candidates = await vector_store.search_lore(
                collection=collection,
                query_vector=query_vector,
                limit=15,
                score_threshold=score_threshold,
            )
        except Exception as e:
            log.warning("Lore parent-child retrieval failed", collection=collection, error=str(e))
            return []

        query_tokens = self.reranker.tokenize(query_text)
        scored_candidates = []
        
        for cand in candidates:
            payload = cand.get("payload", {})
            child_text = payload.get("text_content", "")
            score = cand.get("score", 0.0)
            if child_text:
                keyword_score = self.reranker.calculate_score(query_tokens, child_text)
                hybrid_score = (score * 0.75) + (keyword_score * 0.25)
                scored_candidates.append((cand, hybrid_score))

        scored_candidates.sort(key=lambda x: x[1], reverse=True)

        seen_parents = set()
        lore_chunks = []
        for cand, _ in scored_candidates:
            payload = cand.get("payload", {})
            parent_id = payload.get("parent_id")
            parent_text = payload.get("parent_full_text")
            text = parent_text if parent_text else payload.get("text_content", "")
            if not text:
                continue
            if parent_id:
                if parent_id not in seen_parents:
                    seen_parents.add(parent_id)
                    lore_chunks.append(text)
            else:
                lore_chunks.append(text)
                
        return lore_chunks[:top_k]
