import time
import uuid
from typing import Optional, List

from app.domain.interfaces.embedding_provider import IEmbeddingProvider
from app.domain.entities.memory import MemoryType, MemoryMetadata, MemoryPayload
from app.domain.interfaces.vector_store import IVectorStore
from app.infrastructure.logging.logger import get_logger

log = get_logger(__name__)


class MemoryManager:
    """
    Domain Service responsible for orchestrating Memory lifecycle.
    It bridges Relational Storage (PostgreSQL) and Vector Storage (Qdrant),
    using the injected Embedding Provider.
    """

    def __init__(self, embedder: IEmbeddingProvider, vector_store: IVectorStore):
        self.embedder = embedder
        self.vector_store = vector_store

    def calculate_importance(self, user_message: str, emotion_delta: any) -> float:
        """
        Calculates whether a message is worth storing in Emotional LTM based on heuristics.
        """
        importance = 0.4
        importance += min(0.3, len(user_message) / 500.0)
        
        # Assuming emotion_delta has .joy, .sadness, etc. If it's a dict, we'd use .get
        emotion_magnitude = abs(getattr(emotion_delta, "joy", 0)) + abs(getattr(emotion_delta, "sadness", 0)) + \
                            abs(getattr(emotion_delta, "irritation", 0)) + abs(getattr(emotion_delta, "trust", 0))
        importance += (emotion_magnitude * 2.5)
        
        if any(w in user_message.lower() for w in ["thích", "ghét", "sợ", "buồn", "yêu", "muốn", "tên anh", "anh là"]):
            importance += 0.2
            
        return min(1.0, importance)

    async def save_emotional_memory(
        self,
        user_id: str,
        conversation_id: str,
        message_content: str,
        importance_score: float,
    ) -> None:
        """
        Embeds a high-importance emotional message and stores it in Qdrant Vector DB.
        (Note: Postgres persistence is handled by conversation lifecycle).
        """
        if importance_score < 0.7:
            log.debug("Memory score too low for emotional storage", score=importance_score)
            return

        vector = await self.embedder.embed_text(message_content)
        point_id = str(uuid.uuid4())

        payload = MemoryPayload(
            user_id=user_id,
            conversation_id=conversation_id,
            memory_type=MemoryType.EMOTIONAL.value,
            importance_score=importance_score,
            created_at=int(time.time()),
            text_content=message_content,
        )

        await self.vector_store.upsert_memory(
            collection="emotional_memories",
            point_id=point_id,
            vector=vector,
            payload=payload,
        )
        log.info("Emotional memory embedded and saved to Qdrant", user_id=user_id, point_id=point_id)

    async def save_conversation_summary(
        self,
        user_id: str,
        conversation_id: str,
        summary_text: str,
        importance_score: float = 0.5,
    ) -> None:
        """
        Embeds a compressed conversation summary and stores it in Qdrant.
        """
        vector = await self.embedder.embed_text(summary_text)
        point_id = str(uuid.uuid4())

        payload = MemoryPayload(
            user_id=user_id,
            conversation_id=conversation_id,
            memory_type=MemoryType.SUMMARY.value,
            importance_score=importance_score,
            created_at=int(time.time()),
            text_content=summary_text,
        )

        await self.vector_store.upsert_memory(
            collection="conversation_summaries",
            point_id=point_id,
            vector=vector,
            payload=payload,
        )
        log.info("Conversation summary embedded and saved to Qdrant", user_id=user_id, point_id=point_id)
