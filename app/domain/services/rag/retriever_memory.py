import time
from app.domain.interfaces.vector_store import IVectorStore
from app.domain.services.rag.base import ScoredMemory
from app.domain.services.rag.reranker import HybridMemoryScorer
from app.domain.tuning.memory import MemoryTuning
from app.domain.tuning.rag import RAGTuning
from app.shared.utils.logger import get_logger

log = get_logger(__name__)


class MemoryRetriever:
    """
    Retrieves and ranks user memories from Qdrant using Hybrid Scoring.
    """
    def __init__(self, vector_store: IVectorStore, scorer: HybridMemoryScorer | None = None):
        self.vector_store = vector_store
        self.scorer = scorer or HybridMemoryScorer()

    async def retrieve_memories(
        self,
        collection: str,
        query_vector: list[float],
        user_id: str,
        conversation_id: str | None = None,
        current_emotion: dict[str, float] | None = None,
        limit: int = 15,
        top_k: int = RAGTuning.TOP_K
    ) -> list[ScoredMemory]:
        try:
            candidates = await self.vector_store.search_by_user(
                collection=collection,
                query_vector=query_vector,
                user_id=user_id,
                conversation_id=conversation_id,
                limit=limit,
                score_threshold=0.4
            )
        except Exception as e:
            log.error("Failed to query user memories from Qdrant", user_id=user_id, conversation_id=conversation_id, error=str(e))
            return []

        if not candidates:
            return []

        now = int(time.time())
        scored_memories = []

        for cand in candidates:
            payload = cand["payload"]
            similarity_score = cand["score"]
            
            # Adaptive Ebbinghaus Recency decay with importance modulation
            created_at = payload.get("created_at", now)
            last_accessed_at = payload.get("last_accessed_at")
            importance_score = payload.get("importance_score", MemoryTuning.IMPORTANCE_SCORE)
            memory_type = payload.get("memory_type", "user_fact")

            # Importance boosting by tier
            tier = payload.get("memory_tier", "casual")
            if tier == "critical":
                importance_score = min(1.0, importance_score + MemoryTuning.TIER_BOOST_RELATIONSHIP)
            elif tier == "personal":
                importance_score = min(1.0, importance_score + MemoryTuning.TIER_BOOST_CORE)

            recency_score = self.scorer.calculate_recency(
                created_at=created_at,
                now=now,
                importance=importance_score,
                memory_type=memory_type,
                last_accessed_at=last_accessed_at
            )
                
            # Emotion alignment match
            emotion_match_score = 0.5
            if current_emotion:
                memory_emotions = payload.get("emotion", {})
                emotion_match_score = self.scorer.calculate_emotion_match(memory_emotions, current_emotion)

            final_score = self.scorer.calculate_final_score(
                similarity=similarity_score,
                recency=recency_score,
                importance=importance_score,
                emotion_match=emotion_match_score
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

        scored_memories.sort(key=lambda x: x.final_score, reverse=True)
        return scored_memories[:top_k]
