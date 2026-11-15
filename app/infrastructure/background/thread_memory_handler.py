"""Extract long-term memories from one stored v2 turn, after the reply was sent (MEM-005)."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

from sqlalchemy import select

from app.domain.models.background_job import BackgroundJobType, ClaimedBackgroundJob
from app.domain.services.memory_extractor import MemoryExtractor
from app.infrastructure.background.core_memory_consolidation_handler import (
    ConsolidationJobScheduler,
)
from app.infrastructure.background.job_handlers import (
    BackgroundTurnSourceReader,
    DurableJobPayloadError,
)
from app.infrastructure.database.models.thread import ThreadModel, ThreadTurnModel

HISTORY_TURNS = 5


class ThreadMemoryExtractionJobHandler:
    def __init__(
        self,
        session_factory: Callable[[], Any],
        consent: BackgroundTurnSourceReader,
        extractor: MemoryExtractor,
        consolidation: ConsolidationJobScheduler | None = None,
    ) -> None:
        self._sessions = session_factory
        self._consent = consent
        self._extractor = extractor
        self._consolidation = consolidation

    async def handle(self, job: ClaimedBackgroundJob) -> None:
        if job.job_type is not BackgroundJobType.THREAD_MEMORY_EXTRACTION:
            raise DurableJobPayloadError("job type mismatch")
        user_id, thread_id, turn_id = (_uuid(job.payload, key) for key in _KEYS)
        if user_id != job.principal_id:
            raise DurableJobPayloadError("job payload scope does not match trusted envelope")
        # Consent may have been withdrawn after the turn was stored.
        await self._consent.ensure_consent(user_id)
        turn, earlier = await self._load(user_id, thread_id, turn_id)
        stored = await self._extractor.extract_and_store_batch(
            # The same id v2 recall filters on, so what is stored here is found again.
            user_id=str(user_id),
            conversation_id=str(thread_id),
            history=_history(earlier),
            current_user_message=turn.question,
            current_assistant_reply=turn.answer,
            idempotency_key=job.idempotency_key,
            propagate_errors=True,
        )
        if stored and self._consolidation is not None:
            await self._consolidation.schedule(user_id)

    async def _load(
        self, user_id: uuid.UUID, thread_id: uuid.UUID, turn_id: uuid.UUID
    ) -> tuple[ThreadTurnModel, list[ThreadTurnModel]]:
        owned = (
            select(ThreadTurnModel)
            .join(ThreadModel, ThreadModel.id == ThreadTurnModel.thread_id)
            .where(ThreadModel.owner_principal == str(user_id), ThreadModel.id == thread_id)
        )
        async with self._sessions() as session:
            turn = await session.scalar(owned.where(ThreadTurnModel.turn_id == turn_id))
            if turn is None:
                # Deleted threads and erased users leave nothing to extract from.
                raise DurableJobPayloadError("thread turn is missing or unauthorized")
            earlier = await session.scalars(
                owned.where(ThreadTurnModel.created_at < turn.created_at)
                .order_by(ThreadTurnModel.created_at.desc())
                .limit(HISTORY_TURNS)
            )
            return turn, list(earlier)[::-1]


_KEYS = ("user_id", "thread_id", "turn_id")


def _uuid(payload: dict[str, Any], key: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(payload[key]))
    except (KeyError, TypeError, ValueError) as error:
        raise DurableJobPayloadError(f"invalid {key}") from error


def _history(turns: list[ThreadTurnModel]) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    for turn in turns:
        messages.append({"role": "user", "content": turn.question})
        messages.append({"role": "assistant", "content": turn.answer})
    return messages
