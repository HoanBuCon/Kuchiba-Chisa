import time
import math
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
        top_k: int = 8,
    ) -> List[str]:
        """
        Retrieves relevant Chisa lore chunks from the global `chisa_lore` collection.
        Does not filter by user_id so all users share this core identity.
        """
        try:
            candidates = await qdrant_service.search_lore(
                collection="chisa_lore",
                query_vector=query_vector,
                limit=top_k,
                score_threshold=0.1,
            )
        except Exception as e:
            log.warning("Lore retrieval failed, skipping", error=str(e))
            return []

        results = []
        for cand in candidates:
            text = cand.get("payload", {}).get("text_content", "")
            if text:
                results.append(text)
        return results


# Singleton
rag_retriever = RAGRetriever()
