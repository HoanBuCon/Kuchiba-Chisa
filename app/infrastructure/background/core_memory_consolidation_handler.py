"""Fold new episodic memories into a member's core memory, off the chat path (MEM-005)."""

from __future__ import annotations

import time
import uuid

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.interfaces.background_jobs import IDurableBackgroundJobQueue
from app.domain.interfaces.core_memory_consolidation import (
    ConsolidationState,
    ICoreMemoryConsolidationStore,
)
from app.domain.models.background_job import (
    BackgroundJobSubmission,
    BackgroundJobType,
    ClaimedBackgroundJob,
    CoreMemoryConsolidationPayload,
)
from app.domain.services.core_memory_consolidator import CoreMemoryConsolidator
from app.infrastructure.background.job_handlers import (
    BackgroundTurnSourceReader,
    DurableJobPayloadError,
)
from app.shared.utils.logger import get_logger

log = get_logger(__name__)

# Bounds how long a memory can wait when it lands on a key that already ran (same-second ties).
CONSOLIDATION_WINDOW_SECONDS = 3_600


def consolidation_job(
    user_id: uuid.UUID, state: ConsolidationState, now: float | None = None
) -> BackgroundJobSubmission:
    """Turns before the job runs share its key; once it moves the watermark, the key changes."""
    window = int((time.time() if now is None else now) // CONSOLIDATION_WINDOW_SECONDS)
    # The version is in the key so a job that lost a race to a hand edit can be queued again.
    position = f"{state.consolidated_through}:{state.version or 0}:{window}"
    return BackgroundJobSubmission(
        job_type=BackgroundJobType.CORE_MEMORY_CONSOLIDATION,
        idempotency_key=f"core-memory-consolidation:{user_id}:{position}",
        payload=CoreMemoryConsolidationPayload(user_id).as_json(),
        principal_id=user_id,
    )


class ConsolidationJobScheduler:
    """Queues the job; a failure only delays it, since the watermark catches up later."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        queue: IDurableBackgroundJobQueue,
        store: ICoreMemoryConsolidationStore,
    ) -> None:
        self._sessions = session_factory
        self._queue = queue
        self._store = store

    async def schedule(self, user_id: uuid.UUID) -> None:
        try:
            state = await self._store.load(str(user_id))
            async with self._sessions() as session:
                await self._queue.enqueue(session, consolidation_job(user_id, state))
                await session.commit()
        except (SQLAlchemyError, OSError) as error:
            log.warning("Core memory consolidation was not queued", error_type=type(error).__name__)


class CoreMemoryConsolidationJobHandler:
    def __init__(
        self, consent: BackgroundTurnSourceReader, consolidator: CoreMemoryConsolidator
    ) -> None:
        self._consent = consent
        self._consolidator = consolidator

    async def handle(self, job: ClaimedBackgroundJob) -> None:
        if job.job_type is not BackgroundJobType.CORE_MEMORY_CONSOLIDATION:
            raise DurableJobPayloadError("job type mismatch")
        user_id = _user_id(job.payload)
        if user_id != job.principal_id:
            raise DurableJobPayloadError("job payload scope does not match trusted envelope")
        # Consent may have been withdrawn after the memories were stored.
        await self._consent.ensure_consent(user_id)
        if not await self._consolidator.consolidate(str(user_id)):
            log.info("Core memory changed during consolidation; leaving it for the next job")


def _user_id(payload: dict[str, object]) -> uuid.UUID:
    try:
        return uuid.UUID(str(payload["user_id"]))
    except (KeyError, ValueError) as error:
        raise DurableJobPayloadError("invalid user_id") from error
