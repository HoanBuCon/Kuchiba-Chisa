"""One transaction for a stored turn, its emotion and its outbox jobs (EMO-003, REL-007)."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from app.domain.entities.emotion import EMOTION_DIMENSIONS, EmotionMutation
from app.domain.models.background_job import (
    BackgroundJobSubmission,
    BackgroundJobType,
    ThreadMemoryPayload,
    ThreadSummaryPayload,
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


def summary_job(record: TurnRecord, owner: str, version: int) -> BackgroundJobSubmission:
    """One job per thread and summary version, so a growing backlog queues one call, not many."""
    user_id = normalize_user_id(owner)
    return BackgroundJobSubmission(
        job_type=BackgroundJobType.THREAD_SUMMARY,
        idempotency_key=f"thread-summary:{record.thread_id}:{version}",
        payload=ThreadSummaryPayload(user_id, record.thread_id, record.turn_id).as_json(),
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
        summary_version: int | None = None,
    ) -> bool:
        async with self._sessions() as session:
            stored = bool((await session.execute(turn_insert(record))).rowcount)
            # A retry that lost the race must not move emotion or queue the job again.
            if stored and sentiment:
                await self._move_emotion(session, owner, sentiment)
            if stored and self._queue is not None:
                await self._enqueue_jobs(session, record, owner, remember, summary_version)
            await session.commit()
            return stored

    async def _enqueue_jobs(
        self,
        session: Any,
        record: TurnRecord,
        owner: str,
        remember: bool,
        summary_version: int | None,
    ) -> None:
        if remember:
            await self._queue.enqueue(session, memory_job(record, owner))
        if summary_version is not None:
            await self._queue.enqueue(session, summary_job(record, owner, summary_version))

    async def _move_emotion(self, session: Any, owner: str, sentiment: Mapping[str, Any]) -> None:
        user_id = normalize_user_id(owner)
        repository = SqlAlchemyEmotionRepository(session)
        emotion = await repository.get_emotion_state(user_id)
        delta = self._engine.update(emotion, sentiment_analysis=dict(sentiment))
        mutation = EmotionMutation(**{name: getattr(delta, name) for name in EMOTION_DIMENSIONS})
        await repository.apply_mutation(user_id, mutation, updated_at=emotion.updated_at)
