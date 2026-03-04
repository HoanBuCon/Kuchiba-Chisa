import time
import uuid
from typing import Optional, List

from app.domain.interfaces.embedding_provider import IEmbeddingProvider
from app.infrastructure.database.models.message import Message
from app.infrastructure.database.models.memory_metadata import MemoryType, MemoryMetadata
from app.infrastructure.vector.qdrant.qdrant_service import QdrantService, MemoryPayload
from app.infrastructure.logging.logger import get_logger

log = get_logger(__name__)


class MemoryManager:
    """
    Domain Service responsible for orchestrating Memory lifecycle.
    It bridges Relational Storage (PostgreSQL) and Vector Storage (Qdrant),
    using the injected Embedding Provider.
    """

    def __init__(self, embedder: IEmbeddingProvider, qdrant: QdrantService):
        self.embedder = embedder
        self.qdrant = qdrant

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

        await self.qdrant.upsert_memory(
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

        await self.qdrant.upsert_memory(
            collection="conversation_summaries",
            point_id=point_id,
            vector=vector,
            payload=payload,
        )
        log.info("Conversation summary embedded and saved to Qdrant", user_id=user_id, point_id=point_id)
