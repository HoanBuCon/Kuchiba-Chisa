"""One transaction for a stored turn, its emotion and its outbox job (EMO-003, REL-007)."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from app.domain.entities.emotion import EMOTION_DIMENSIONS, EmotionMutation
from app.domain.models.background_job import (
    BackgroundJobSubmission,
    BackgroundJobType,
    ThreadMemoryPayload,
)
from app.domain.models.thread import TurnRecord
from app.domain.services.emotion_engine import EmotionEngine
from app.infrastructure.database.repositories.emotion_repository import (
    SqlAlchemyEmotionRepository,
)
from app.infrastructure.database.repositories.thread_store import turn_insert
from app.shared.utils.user_identity import normalize_user_id


def memory_job(record: TurnRecord, owner: str) -> BackgroundJobSubmission:
    user_id = normalize_user_id(owner)
    return BackgroundJobSubmission(
        job_type=BackgroundJobType.THREAD_MEMORY_EXTRACTION,
        idempotency_key=f"thread-memory:{record.thread_id}:{record.turn_id}",
        payload=ThreadMemoryPayload(user_id, record.thread_id, record.turn_id).as_json(),
        principal_id=user_id,
    )


class PostgresTurnCommit:
    def __init__(
        self,
        session_factory: Callable[[], Any],
        queue: Any = None,
        engine: EmotionEngine | None = None,
    ) -> None:
        self._sessions = session_factory
        self._queue = queue
        self._engine = engine or EmotionEngine()

    async def commit(
        self,
        record: TurnRecord,
        owner: str,
        sentiment: Mapping[str, Any],
        *,
        remember: bool = False,
    ) -> bool:
        async with self._sessions() as session:
            stored = bool((await session.execute(turn_insert(record))).rowcount)
            # A retry that lost the race must not move emotion or queue the job again.
            if stored and sentiment:
                await self._move_emotion(session, owner, sentiment)
            if stored and remember and self._queue is not None:
                await self._queue.enqueue(session, memory_job(record, owner))
            await session.commit()
            return stored

    async def _move_emotion(self, session: Any, owner: str, sentiment: Mapping[str, Any]) -> None:
        user_id = normalize_user_id(owner)
        repository = SqlAlchemyEmotionRepository(session)
        emotion = await repository.get_emotion_state(user_id)
        delta = self._engine.update(emotion, sentiment_analysis=dict(sentiment))
        mutation = EmotionMutation(**{name: getattr(delta, name) for name in EMOTION_DIMENSIONS})
        await repository.apply_mutation(user_id, mutation, updated_at=emotion.updated_at)
