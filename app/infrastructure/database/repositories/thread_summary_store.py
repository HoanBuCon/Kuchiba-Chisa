"""Rolling thread summaries, versioned so a slow job never overwrites (CONV-002)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError

from app.domain.models.thread import ThreadSummary
from app.infrastructure.database.models.thread import ThreadSummaryModel

FIRST_VERSION = 1


def _first_version(thread_id: UUID, summary: str, covered_turn_id: UUID) -> Any:
    return (
        insert(ThreadSummaryModel)
        .values(
            thread_id=thread_id,
            summary=summary,
            version=FIRST_VERSION,
            covered_turn_id=covered_turn_id,
        )
        .on_conflict_do_nothing(index_elements=[ThreadSummaryModel.thread_id])
    )


def _next_version(thread_id: UUID, summary: str, covered_turn_id: UUID, expected: int) -> Any:
    return (
        update(ThreadSummaryModel)
        .where(ThreadSummaryModel.thread_id == thread_id, ThreadSummaryModel.version == expected)
        .values(
            summary=summary,
            version=expected + 1,
            covered_turn_id=covered_turn_id,
            updated_at=func.now(),
        )
    )


class PostgresThreadSummaryStore:
    def __init__(self, session_factory: Callable[[], Any]) -> None:
        self._sessions = session_factory

    async def get(self, thread_id: UUID) -> ThreadSummary | None:
        async with self._sessions() as session:
            row = await session.scalar(
                select(ThreadSummaryModel).where(ThreadSummaryModel.thread_id == thread_id)
            )
            if row is None:
                return None
            return ThreadSummary(row.summary, row.version, row.covered_turn_id)

    async def save(
        self,
        thread_id: UUID,
        summary: str,
        covered_turn_id: UUID,
        *,
        expected_version: int | None,
    ) -> bool:
        if expected_version is None:
            statement = _first_version(thread_id, summary, covered_turn_id)
        else:
            statement = _next_version(thread_id, summary, covered_turn_id, expected_version)
        async with self._sessions() as session:
            try:
                result = await session.execute(statement)
                await session.commit()
            except IntegrityError:
                # The thread was deleted while the job ran, and its summary went with it.
                return False
            return bool(result.rowcount)
