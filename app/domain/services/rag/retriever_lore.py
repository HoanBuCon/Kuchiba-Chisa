from typing import List, Tuple, Optional, Callable, Any
from app.domain.interfaces.vector_store import IVectorStore
from app.domain.interfaces.repositories import ILoreParentRepository
from app.domain.services.rag.reranker import KeywordOverlapReranker
from app.domain.tuning.rag import RAGTuning
from app.shared.utils.logger import get_logger
import uuid

log = get_logger(__name__)


class LoreRetriever:
    """
    Retrieves Chisa lore chunks from Qdrant using vector search,
    boosted by keyword overlap re-ranking.
    """
    def __init__(
        self, 
        vector_store: IVectorStore, 
        reranker: Optional[KeywordOverlapReranker] = None,
        lore_parent_repo_factory: Optional[Callable[[Any], ILoreParentRepository]] = None
    ):
        self.vector_store = vector_store
        self.reranker = reranker or KeywordOverlapReranker()
        self.lore_parent_repo_factory = lore_parent_repo_factory

    async def retrieve_lore_standard(
        self,
        query_vector: List[float],
        query_text: str = "",
        top_k: int = 8,
        score_threshold: float = 0.3,
    ) -> List[Tuple[str, float]]:
        try:
            if not self.vector_store:
                return []
            
            candidates = await self.vector_store.search_lore(
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
        collection: str,
        query_vector: List[float],
        session: Any = None,
        query_text: str = "",
        top_k: int = RAGTuning.TOP_K,
        score_threshold: float = RAGTuning.SCORE_THRESHOLD,
        entities_filter: Optional[List[str]] = None,
    ) -> List[Tuple[str, float]]:
        try:
            if not self.vector_store:
                return []
                
            candidates = await self.vector_store.search_lore(
                collection=collection,
                query_vector=query_vector,
                limit=15,
                score_threshold=score_threshold,
                entities_filter=entities_filter,
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
        
        # We need to collect parent IDs to fetch them from DB
        parent_ids_to_fetch = set()
        for cand, score in scored_candidates:
            payload = cand.get("payload", {})
            parent_id_str = payload.get("parent_id")
            if parent_id_str:
                try:
                    parent_ids_to_fetch.add(uuid.UUID(parent_id_str))
                except ValueError:
                    pass

        # Fetch parents if repo factory and session are provided
        parent_docs = {}
        if self.lore_parent_repo_factory and session and parent_ids_to_fetch:
            repo = self.lore_parent_repo_factory(session)
            parents = await repo.get_parents_batch(list(parent_ids_to_fetch))
            for p in parents:
                parent_docs[str(p.id)] = p.full_text

        for cand, score in scored_candidates:
            payload = cand.get("payload", {})
            parent_id = payload.get("parent_id")
            
            # 1. Try to get full text from DB
            text = parent_docs.get(parent_id) if parent_id else None
            
            # 2. Fallback to child chunk text
            if not text:
                text = payload.get("text_content", "")
                
            if not text:
                continue
                
            if parent_id:
                if parent_id not in seen_parents:
                    seen_parents.add(parent_id)
                    lore_chunks.append((text, score))
            else:
                lore_chunks.append((text, score))
                
        return lore_chunks[:top_k]
