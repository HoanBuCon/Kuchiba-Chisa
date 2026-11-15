"""Roll the older turns of a v2 thread into its summary, after the reply was sent (CONV-003)."""

from __future__ import annotations

import uuid
from collections.abc import Callable, Sequence
from typing import Any, Protocol

from sqlalchemy import select

from app.domain.interfaces.threads import IThreadSummaryStore
from app.domain.models.background_job import BackgroundJobType, ClaimedBackgroundJob
from app.domain.models.thread import ThreadSummary
from app.domain.services.conversation_window import SUMMARY_KEEP_RECENT_TURNS
from app.domain.services.knowledge.understanding import PriorTurn
from app.infrastructure.background.job_handlers import DurableJobPayloadError, payload_uuid
from app.infrastructure.database.models.thread import ThreadModel, ThreadTurnModel
from app.infrastructure.logging.logger import get_logger

log = get_logger(__name__)

# One summary call stays small; a longer backlog is caught up by the next job.
MAX_TURNS_PER_SUMMARY = 30
_KEYS = ("user_id", "thread_id", "through_turn_id")


class IThreadSummarizer(Protocol):
    async def summarize(self, previous: str | None, turns: Sequence[PriorTurn]) -> str: ...


class ThreadSummaryJobHandler:
    def __init__(
        self,
        session_factory: Callable[[], Any],
        summaries: IThreadSummaryStore,
        summarizer: IThreadSummarizer,
    ) -> None:
        self._sessions = session_factory
        self._summaries = summaries
        self._summarizer = summarizer

    async def handle(self, job: ClaimedBackgroundJob) -> None:
        if job.job_type is not BackgroundJobType.THREAD_SUMMARY:
            raise DurableJobPayloadError("job type mismatch")
        user_id, thread_id, through = (payload_uuid(job.payload, key) for key in _KEYS)
        if user_id != job.principal_id:
            raise DurableJobPayloadError("job payload scope does not match trusted envelope")
        current = await self._summaries.get(thread_id)
        turns = await self._uncovered(user_id, thread_id, through, current)
        # The newest turns stay verbatim in the window, so only the ones before them are folded in.
        covered = turns[: max(0, len(turns) - SUMMARY_KEEP_RECENT_TURNS)][:MAX_TURNS_PER_SUMMARY]
        if not covered:
            return
        text = await self._summarizer.summarize(
            current.summary if current else None,
            [PriorTurn(turn.question, turn.answer) for turn in covered],
        )
        version = current.version if current else None
        saved = await self._summaries.save(
            thread_id, text, covered[-1].turn_id, expected_version=version
        )
        if not saved:
            # Another job or a deleted thread got there first; overwriting would lose its work.
            log.info("Thread summary skipped after a lost race", thread_id=str(thread_id))

    async def _uncovered(
        self,
        user_id: uuid.UUID,
        thread_id: uuid.UUID,
        through: uuid.UUID,
        current: ThreadSummary | None,
    ) -> list[ThreadTurnModel]:
        def owned(*columns: Any) -> Any:
            return (
                select(*columns)
                .join(ThreadModel, ThreadModel.id == ThreadTurnModel.thread_id)
                .where(ThreadModel.owner_principal == str(user_id), ThreadModel.id == thread_id)
            )

        async with self._sessions() as session:
            through_at = await session.scalar(
                owned(ThreadTurnModel.created_at).where(ThreadTurnModel.turn_id == through)
            )
            if through_at is None:
                # A deleted thread or an erased user leaves nothing to summarize.
                return []
            query = owned(ThreadTurnModel).where(ThreadTurnModel.created_at <= through_at)
            if current is not None:
                covered_at = await session.scalar(
                    owned(ThreadTurnModel.created_at).where(
                        ThreadTurnModel.turn_id == current.covered_turn_id
                    )
                )
                if covered_at is not None:
                    query = query.where(ThreadTurnModel.created_at > covered_at)
            rows = await session.scalars(query.order_by(ThreadTurnModel.created_at))
            return list(rows)
