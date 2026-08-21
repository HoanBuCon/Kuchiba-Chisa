from typing import List, Tuple, Optional, Callable, Any, Dict
from app.domain.interfaces.vector_store import IVectorStore
from app.domain.interfaces.repositories import ILoreParentRepository
from app.domain.services.rag.reranker import KeywordOverlapReranker
from app.domain.tuning.rag import RAGTuning
from app.shared.utils.logger import get_logger
import uuid

from app.shared.utils.token_estimator import TokenEstimator

log = get_logger(__name__)


class LoreRetriever:
    """
    Retrieves Chisa lore chunks from Qdrant using vector search,
    boosted by keyword overlap re-ranking and Windowed Parent Resolution.
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

    @staticmethod
    def resolve_windowed_parent(parent_markdown: Optional[str], child_text: str, window_chars: int = 1200) -> str:
        """
        Extracts a localized context window around child_text instead of loading the entire parent markdown.
        Prevents Parent Document Bloat and token starvation.
        """
        if not parent_markdown:
            return child_text
        if not child_text:
            return parent_markdown[:window_chars].strip()

        # If parent markdown is already compact, use it directly
        if len(parent_markdown) <= window_chars:
            return parent_markdown.strip()

        # Find position of child chunk in parent document
        pos = parent_markdown.find(child_text[:80])
        if pos == -1:
            pos = parent_markdown.find(child_text[:40])

        if pos == -1:
            return child_text

        half_window = window_chars // 2
        start = max(0, pos - half_window)
        end = min(len(parent_markdown), pos + len(child_text) + half_window)

        # Align start boundary to newline if close
        if start > 0:
            prev_nl = parent_markdown.rfind("\n", 0, start)
            if prev_nl != -1 and (start - prev_nl) < 200:
                start = prev_nl + 1

        # Align end boundary to newline if close
        if end < len(parent_markdown):
            next_nl = parent_markdown.find("\n", end)
            if next_nl != -1 and (next_nl - end) < 200:
                end = next_nl

        snippet = parent_markdown[start:end].strip()
        prefix = "... " if start > 0 else ""
        suffix = " ..." if end < len(parent_markdown) else ""
        return f"{prefix}{snippet}{suffix}"

    async def retrieve_lore_parent_child(
        self,
        collection: str,
        query_vector: List[float],
        session: Any = None,
        query_text: str = "",
        top_k: int = RAGTuning.TOP_K,
        score_threshold: float = RAGTuning.SCORE_THRESHOLD,
        entities_filter: Optional[List[str]] = None,
        max_token_budget: Optional[int] = None,
    ) -> List[Tuple[str, float, Dict[str, Any]]]:
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
        filter_set = set(entities_filter) if entities_filter else set()
        scored_candidates = []
        
        for cand in candidates:
            payload = cand.get("payload", {})
            child_text = payload.get("text_content", "")
            score = cand.get("score", 0.0)
            if child_text:
                # 1. Text Keyword Overlap Score
                keyword_score = self.reranker.calculate_score(query_tokens, child_text)
                
                # 2. Metadata Overlap & Entity Alignment Score
                canon_name = payload.get("canonical_name") or ""
                heading = payload.get("heading_path") or ""
                meta_text = f"{canon_name} {heading}".strip()
                heading_score = self.reranker.calculate_score(query_tokens, meta_text) if meta_text else 0.0
                
                chunk_entities = payload.get("entities") or []
                entity_hit = 1.0 if (filter_set and (any(e in filter_set for e in chunk_entities) or canon_name in filter_set)) else 0.0
                metadata_score = (heading_score * 0.5) + (entity_hit * 0.5)
                
                # 3. Unified Multi-Signal Hybrid Score
                hybrid_score = (
                    (score * RAGTuning.WEIGHT_VECTOR) +
                    (keyword_score * RAGTuning.WEIGHT_KEYWORD) +
                    (metadata_score * RAGTuning.WEIGHT_METADATA)
                )
                
                scoring_meta = {
                    "collection": collection,
                    "source_type": payload.get("source_type", "wiki"),
                    "vector_score": round(score, 4),
                    "keyword_score": round(keyword_score, 4),
                    "metadata_score": round(metadata_score, 4),
                    "hybrid_score": round(hybrid_score, 4),
                    "canonical_name": canon_name,
                    "heading_path": heading,
                    "entities": chunk_entities,
                    "entity_hit": bool(entity_hit)
                }
                cand["scoring_meta"] = scoring_meta
                scored_candidates.append((cand, hybrid_score))

        scored_candidates.sort(key=lambda x: x[1], reverse=True)

        seen_parents = set()
        lore_chunks = []
        accumulated_tokens = 0
        
        # Collect parent IDs to fetch from DB
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
            try:
                repo = self.lore_parent_repo_factory(session)
                parents = await repo.get_parents_batch(list(parent_ids_to_fetch))
                for p in parents:
                    # Store full parent section markdown
                    parent_docs[str(p.id)] = p.markdown
            except Exception as pe:
                log.warning("Failed to fetch parent markdown from database, using chunk fallback", error=str(pe))

        for cand, score in scored_candidates:
            payload = cand.get("payload", {})
            parent_id = payload.get("parent_id")
            
            # 1. Try to get section parent markdown from DB
            parent_text = parent_docs.get(parent_id) if parent_id else None
            child_text = payload.get("text_content", "")
            
            # 2. Windowed Parent Resolution (mitigate parent bloat)
            resolved_text = self.resolve_windowed_parent(parent_text, child_text, window_chars=1200) if parent_text else child_text
            
            if not resolved_text:
                continue
                
            chunk_tokens = TokenEstimator.estimate(resolved_text)
            
            # Check dynamic context token budget if provided
            if max_token_budget is not None and accumulated_tokens + chunk_tokens > max_token_budget and lore_chunks:
                log.info("Lore retrieval reached max token budget limit", current_tokens=accumulated_tokens, budget=max_token_budget)
                break
                
            scoring_meta = cand.get("scoring_meta", {})
            if parent_id:
                if parent_id not in seen_parents:
                    seen_parents.add(parent_id)
                    lore_chunks.append((resolved_text, score, scoring_meta))
                    accumulated_tokens += chunk_tokens
            else:
                lore_chunks.append((resolved_text, score, scoring_meta))
                accumulated_tokens += chunk_tokens
                
            if len(lore_chunks) >= top_k:
                break
                
        return lore_chunks
