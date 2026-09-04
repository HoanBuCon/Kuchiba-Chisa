import time

from app.domain.interfaces.vector_store import IVectorStore
from app.domain.services.rag.base import ScoredMemory
from app.domain.services.rag.reranker import HybridMemoryScorer
from app.shared.utils.logger import get_logger

log = get_logger(__name__)


class GuildMemoryRetriever:
    """
    Retrieves and ranks server-level shared memories, events, and culture from Qdrant.
    Enforces guild_id isolation and optionally filters out expired events.
    """
    def __init__(self, vector_store: IVectorStore, scorer: HybridMemoryScorer | None = None):
        self.vector_store = vector_store
        self.scorer = scorer or HybridMemoryScorer()

    async def retrieve_guild_memories(
        self,
        collection: str,
        query_vector: list[float],
        guild_id: str,
        channel_id: str | None = None,
        limit: int = 10,
        top_k: int = 3,
        score_threshold: float = 0.45,
        exclude_expired: bool = True
    ) -> list[ScoredMemory]:
        if not guild_id or guild_id.startswith("CHANNEL_") or guild_id == "DM":
            return []

        try:
            candidates = await self.vector_store.search_guild_memories(
                collection=collection,
                query_vector=query_vector,
                guild_id=guild_id,
                channel_id=channel_id,
                limit=limit,
                score_threshold=score_threshold,
                exclude_expired=exclude_expired
            )
        except Exception as e:
            log.error("Failed to query guild memories from Qdrant", guild_id=guild_id, error=str(e))
            return []

        if not candidates:
            return []

        now = int(time.time())
        scored_memories = []

        for cand in candidates:
            payload = cand.get("payload") or cand.get("metadata") or {}
            similarity_score = cand.get("score", 0.0)
            text_content = payload.get("text_content") or cand.get("text") or ""
            
            created_at = payload.get("created_at", now)
            expires_at = payload.get("expires_at")
            importance_score = payload.get("importance_score", 0.75)
            memory_type = payload.get("memory_type", "guild_event")
            tier = payload.get("memory_tier", "personal")

            # If event has expired and wasn't filtered by Qdrant, skip it
            if exclude_expired and expires_at and expires_at <= now:
                continue

            # Boost active upcoming events
            if memory_type == "guild_event":
                importance_score = min(1.0, importance_score + 0.10)

            recency_score = self.scorer.calculate_recency(
                created_at=created_at,
                now=now,
                importance=importance_score,
                memory_type=memory_type
            )

            final_score = self.scorer.calculate_final_score(
                similarity=similarity_score,
                recency=recency_score,
                importance=importance_score,
                emotion_match=0.5
            )

            scored_memories.append(
                ScoredMemory(
                    id=str(cand.get("id", "")),
                    text_content=text_content,
                    memory_type=memory_type,
                    memory_tier=tier,
                    final_score=final_score,
                    metadata=payload,
                    components={
                        "similarity": similarity_score,
                        "recency": recency_score,
                        "importance": importance_score,
                        "emotion": 0.5
                    }
                )
            )

        scored_memories.sort(key=lambda x: x.final_score, reverse=True)
        return scored_memories[:top_k]
