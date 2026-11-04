"""RESONA, consent and memory recall for v2 turns, reusing v1 repositories (EMO-001, MEM-002)."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from sqlalchemy.exc import SQLAlchemyError

from app.domain.entities.emotion import EMOTION_DIMENSIONS, EmotionMutation, EmotionState
from app.domain.interfaces.embedding_provider import IEmbeddingProvider
from app.domain.interfaces.personal_context import ICoreMemoryStore, PersonalContext
from app.domain.services.core_memory import render_core_memory
from app.domain.services.emotion_engine import EmotionEngine
from app.domain.services.rag.retriever_memory import MemoryRetriever
from app.infrastructure.database.repositories.emotion_repository import (
    SqlAlchemyEmotionRepository,
)
from app.infrastructure.database.repositories.privacy_preference import (
    SqlAlchemyPrivacyPreferenceRepository,
)
from app.infrastructure.database.repositories.user_repository import SqlAlchemyUserRepository
from app.shared.utils.user_identity import normalize_user_id

MEMORY_COLLECTION = "memories"
RECALL_CANDIDATES = 10
RECALL_TOP_K = 5
QUERY_PREFIX = "query: "


class PostgresPersonalContext:
    def __init__(
        self,
        session_factory: Callable[[], Any],
        retriever: MemoryRetriever,
        embedder: IEmbeddingProvider,
        core_memory: ICoreMemoryStore,
        engine: EmotionEngine | None = None,
    ) -> None:
        self._sessions = session_factory
        self._retriever = retriever
        self._embedder = embedder
        self._core_memory = core_memory
        self._engine = engine or EmotionEngine()

    async def load(self, owner: str, *, is_guest: bool, question: str) -> PersonalContext:
        user_id = normalize_user_id(owner)
        async with self._sessions() as session:
            await SqlAlchemyUserRepository(session).get_or_create_user(user_id)
            emotion = await SqlAlchemyEmotionRepository(session).get_emotion_state(user_id)
            policy = await SqlAlchemyPrivacyPreferenceRepository(session).get_memory_policy(user_id)
            await session.commit()
        if is_guest or not policy.allows_long_term_memory:
            return PersonalContext(emotion)
        memories, degraded = await self._memories(owner, str(user_id), emotion, question)
        return PersonalContext(emotion, memories, degraded)

    async def _memories(
        self, owner: str, user_id: str, emotion: EmotionState, question: str
    ) -> tuple[tuple[str, ...], tuple[str, ...]]:
        lines: list[str] = []
        degraded: list[str] = []
        try:
            core = render_core_memory(await self._core_memory.get(owner))
            if core:
                lines.append(core)
        except SQLAlchemyError:
            degraded.append("core_memory_failed")
        vector = await self._embedder.embed_text(question, prefix=QUERY_PREFIX)
        recalled = await self._retriever.retrieve_memories(
            collection=MEMORY_COLLECTION,
            query_vector=vector,
            user_id=user_id,
            current_emotion=emotion.values(),
            limit=RECALL_CANDIDATES,
            top_k=RECALL_TOP_K,
        )
        lines.extend(memory.text_content for memory in recalled)
        return tuple(lines), tuple(degraded)

    async def apply_sentiment(self, owner: str, sentiment: Mapping[str, Any]) -> None:
        user_id = normalize_user_id(owner)
        async with self._sessions() as session:
            repository = SqlAlchemyEmotionRepository(session)
            emotion = await repository.get_emotion_state(user_id)
            delta = self._engine.update(emotion, sentiment_analysis=dict(sentiment))
            mutation = EmotionMutation(
                **{name: getattr(delta, name) for name in EMOTION_DIMENSIONS}
            )
            await repository.apply_mutation(user_id, mutation, updated_at=emotion.updated_at)
            await session.commit()

    async def current_emotion(self, owner: str) -> EmotionState | None:
        user_id = normalize_user_id(owner)
        try:
            async with self._sessions() as session:
                await SqlAlchemyUserRepository(session).get_or_create_user(user_id)
                emotion = await SqlAlchemyEmotionRepository(session).get_emotion_state(user_id)
                await session.commit()
        except SQLAlchemyError:
            return None
        return emotion
