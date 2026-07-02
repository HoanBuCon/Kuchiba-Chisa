import time
import math
import re
from typing import Any, List, Dict
from pydantic import BaseModel
from app.infrastructure.vector.qdrant.qdrant_service import qdrant_service
from app.infrastructure.logging.logger import get_logger

log = get_logger(__name__)


class ScoredMemory(BaseModel):
    id: str
    text_content: str
    memory_type: str
    memory_tier: str
    final_score: float
    components: Dict[str, float]


class RAGRetriever:
    """
    Retrieves and ranks memories from Qdrant using a custom Hybrid Scoring formula.
    Strictly isolated by user_id.
    """

    def __init__(self):
        # Hybrid Scoring Weights
        self.W_SIMILARITY = 0.60
        self.W_RECENCY = 0.20
        self.W_IMPORTANCE = 0.15
        self.W_EMOTION = 0.05
        
        # Recency decay constant (lambda). Higher = decays faster
        self.DECAY_LAMBDA = 0.05

    def _calculate_recency_score(self, created_at: int, now: int) -> float:
        """
        Calculates exponential decay based on age in days.
        Score is 1.0 for brand new memories, approaching 0.0 for very old ones.
        """
        age_seconds = max(0, now - created_at)
        age_days = age_seconds / 86400.0
        return math.exp(-self.DECAY_LAMBDA * age_days)

    def _calculate_emotion_match(self, memory_emotion: Dict[str, float], current_emotion: Dict[str, float]) -> float:
        """
        Calculates how closely the user's emotion when the memory was formed 
        matches their current emotion using a simple Euclidean distance inverse or dot product.
        """
        if not memory_emotion or not current_emotion:
            return 0.5 # Neutral fallback if missing data
            
        # Simplified dot-product proxy for matching dimensional emotional states
        score = 0.0
        keys = set(memory_emotion.keys()).intersection(current_emotion.keys())
        if not keys:
            return 0.5
            
        for k in keys:
            # How close are they? (1.0 - absolute difference)
            diff = abs(memory_emotion[k] - current_emotion.get(k, 0.0))
            score += max(0.0, 1.0 - diff)
            
        return score / len(keys)

    @staticmethod
    def _tokenize_query(text: str) -> list[str]:
        tokens = re.findall(r"[\wÀ-ỹ]+", text.lower())
        return [token for token in tokens if len(token) >= 2]

    def _calculate_keyword_overlap(self, query_tokens: list[str], candidate_text: str) -> float:
        if not query_tokens or not candidate_text:
            return 0.0

        candidate_lower = candidate_text.lower()
        hits = 0
        weighted_hits = 0.0

        high_value_terms = {
            "honami", "sumika", "tacet", "vòng", "cổ", "vòng cổ", "startorch",
            "học viện", "broadblade", "kéo", "havoc", "overclock", "sonoro", "sphere",
            "nhật ký", "ký ức", "trà", "pocky", "mèo", "socola", "đam mê", "sở thích", "yêu thích", "đặc biệt", "đáng nhớ"
        }

        for token in query_tokens:
            if token in candidate_lower:
                hits += 1
                weighted_hits += 2.0 if token in high_value_terms else 1.0

        if not hits:
            return 0.0

        return min(1.0, weighted_hits / max(4.0, len(query_tokens)))

    async def retrieve_memories(
        self,
        collection: str,
        query_vector: List[float],
        user_id: str,
        current_emotion: Dict[str, float] = None,
        limit: int = 15,
        top_k: int = 8
    ) -> List[ScoredMemory]:
        """
        Retrieves candidate vectors and applies Hybrid Scoring in-memory.
        """
        # 1. Strict user_id search (semantic candidates)
        candidates = await qdrant_service.search_by_user(
            collection=collection,
            query_vector=query_vector,
            user_id=user_id,
            limit=limit,
            score_threshold=0.4 # Minimum semantic bar
        )

        if not candidates:
            return []

        now = int(time.time())
        scored_memories = []

        # 2. Apply Custom Hybrid Scoring formula
        for cand in candidates:
            payload = cand["payload"]
            similarity_score = cand["score"] # Cosine similarity from Qdrant [0.0 - 1.0]
            
            # Recency
            created_at = payload.get("created_at", now)
            recency_score = self._calculate_recency_score(created_at, now)
            
            # Importance (can be boosted by tier if desired, but base importance is 0-1)
            importance_score = payload.get("importance_score", 0.5)
            tier = payload.get("memory_tier", "casual")
            
            # Tier boosting (optional subtle modifier, or handled strictly by importance)
            if tier == "critical":
                importance_score = min(1.0, importance_score + 0.2)
            elif tier == "personal":
                importance_score = min(1.0, importance_score + 0.1)
                
            # Emotion Match
            emotion_match_score = 0.5
            if current_emotion:
                memory_emotions = payload.get("emotion", {})
                emotion_match_score = self._calculate_emotion_match(memory_emotions, current_emotion)

            # Final Score Calculation
            final_score = (
                (similarity_score * self.W_SIMILARITY) +
                (recency_score * self.W_RECENCY) +
                (importance_score * self.W_IMPORTANCE) +
                (emotion_match_score * self.W_EMOTION)
            )

            scored_memories.append(
                ScoredMemory(
                    id=cand["id"],
                    text_content=payload.get("text_content", ""),
                    memory_type=payload.get("memory_type", "fact"),
                    memory_tier=tier,
                    final_score=final_score,
                    components={
                        "similarity": similarity_score,
                        "recency": recency_score,
                        "importance": importance_score,
                        "emotion": emotion_match_score
                    }
                )
            )

        # 3. Sort DESC by final hybrid score and truncate to top_k
        scored_memories.sort(key=lambda x: x.final_score, reverse=True)
        return scored_memories[:top_k]

    async def retrieve_lore(
        self,
        query_vector: List[float],
        query_text: str = "",
        top_k: int = 8,
        score_threshold: float = 0.3,
    ) -> List[tuple[str, float]]:
        """
        Retrieves relevant Chisa lore chunks from the global `chisa_lore` collection.
        Returns list of (text_content, similarity_score) tuples sorted by score DESC.
        The caller is responsible for applying its own quality threshold.
        """
        try:
            candidates = await qdrant_service.search_lore(
                collection="chisa_lore",
                query_vector=query_vector,
                limit=top_k,
                score_threshold=score_threshold,
            )
        except Exception as e:
            log.warning("Lore retrieval failed, skipping", error=str(e))
            return []

        query_tokens = self._tokenize_query(query_text)
        results = []
        for cand in candidates:
            text = cand.get("payload", {}).get("text_content", "")
            score = cand.get("score", 0.0)
            if text:
                keyword_score = self._calculate_keyword_overlap(query_tokens, text)
                hybrid_score = (score * 0.75) + (keyword_score * 0.25)
                results.append((text, hybrid_score))

        # Favor exact lore facts when keyword overlap is strong enough.
        results.sort(key=lambda item: item[1], reverse=True)
        return results

    async def retrieve_lore_parent_child(
        self,
        collection: str,
        query_vector: List[float],
        query_text: str = "",
        top_k: int = 6,
        score_threshold: float = 0.35,
    ) -> List[str]:
        """
        Retrieves relevant lore chunks using parent-child retrieval schema
        and hybrid keyword re-ranking. Returns deduplicated parent texts.
        """
        try:
            candidates = await qdrant_service.search_lore(
                collection=collection,
                query_vector=query_vector,
                limit=15,  # Fetch more to allow for keyword boosting and deduplication
                score_threshold=score_threshold,
            )
        except Exception as e:
            log.warning("Lore parent-child retrieval failed", collection=collection, error=str(e))
            return []

        query_tokens = self._tokenize_query(query_text)
        scored_candidates = []
        
        for cand in candidates:
            payload = cand.get("payload", {})
            child_text = payload.get("text_content", "")
            score = cand.get("score", 0.0)
            if child_text:
                keyword_score = self._calculate_keyword_overlap(query_tokens, child_text)
                hybrid_score = (score * 0.75) + (keyword_score * 0.25)
                scored_candidates.append((cand, hybrid_score))

        # Sort by hybrid score descending
        scored_candidates.sort(key=lambda x: x[1], reverse=True)

        # Deduplicate parent-child
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


# Singleton
rag_retriever = RAGRetriever()
