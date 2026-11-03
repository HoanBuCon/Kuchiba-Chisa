"""Postgres threads and turns; every read and write is scoped to the owner (CONV-001)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert

from app.domain.models.thread import ChatMode, DowngradeReason, Thread, TurnRecord
from app.infrastructure.database.models.thread import ThreadModel, ThreadTurnModel


def _thread(row: ThreadModel) -> Thread:
    return Thread(
        id=row.id,
        owner_principal=row.owner_principal,
        channel=row.channel,
        mode=ChatMode(row.mode),
        title=row.title,
        created_at=row.created_at,
        archived_at=row.archived_at,
    )


def _turn(row: ThreadTurnModel) -> TurnRecord:
    reason = row.downgrade_reason
    return TurnRecord(
        thread_id=row.thread_id,
        turn_id=row.turn_id,
        question=row.question,
        answer=row.answer,
        mode_requested=ChatMode(row.mode_requested),
        mode_effective=ChatMode(row.mode_effective),
        lane=row.lane,
        status=row.status,
        downgrade_reason=DowngradeReason(reason) if reason else None,
        llm_calls=row.llm_calls,
        citations=tuple(row.citations),
        degraded=tuple(row.degraded),
    )


class PostgresThreadStore:
    def __init__(self, session_factory: Callable[[], Any]) -> None:
        self._sessions = session_factory

    async def create(self, owner: str, channel: str, mode: ChatMode) -> Thread:
        async with self._sessions() as session:
            row = ThreadModel(owner_principal=owner, channel=channel, mode=mode.value)
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return _thread(row)

    async def _owned(self, session: Any, thread_id: UUID, owner: str) -> ThreadModel | None:
        return await session.scalar(
            select(ThreadModel).where(
                ThreadModel.id == thread_id, ThreadModel.owner_principal == owner
            )
        )

    async def get(self, thread_id: UUID, owner: str) -> Thread | None:
        async with self._sessions() as session:
            row = await self._owned(session, thread_id, owner)
            return _thread(row) if row else None

    async def list_for(self, owner: str, limit: int) -> list[Thread]:
        async with self._sessions() as session:
            rows = await session.scalars(
                select(ThreadModel)
                .where(ThreadModel.owner_principal == owner)
                .order_by(ThreadModel.created_at.desc())
                .limit(limit)
            )
            return [_thread(row) for row in rows]

    async def update(
        self, thread_id: UUID, owner: str, *, title: str | None, mode: ChatMode | None
    ) -> Thread | None:
        async with self._sessions() as session:
            row = await self._owned(session, thread_id, owner)
            if row is None:
                return None
            if title is not None:
                row.title = title
            if mode is not None:
                row.mode = mode.value
            await session.commit()
            await session.refresh(row)
            return _thread(row)

    async def delete(self, thread_id: UUID, owner: str) -> bool:
        async with self._sessions() as session:
            result = await session.execute(
                delete(ThreadModel).where(
                    ThreadModel.id == thread_id, ThreadModel.owner_principal == owner
                )
            )
            await session.commit()
            return bool(result.rowcount)

    async def find_turn(self, thread_id: UUID, turn_id: UUID) -> TurnRecord | None:
        async with self._sessions() as session:
            row = await session.scalar(
                select(ThreadTurnModel).where(
                    ThreadTurnModel.thread_id == thread_id, ThreadTurnModel.turn_id == turn_id
                )
            )
            return _turn(row) if row else None

    async def save_turn(self, record: TurnRecord) -> None:
        """Two racing retries of one turn store it once, by the unique constraint."""
        reason = record.downgrade_reason
        async with self._sessions() as session:
            await session.execute(
                insert(ThreadTurnModel)
                .values(
                    thread_id=record.thread_id,
                    turn_id=record.turn_id,
                    question=record.question,
                    answer=record.answer,
                    mode_requested=record.mode_requested.value,
                    mode_effective=record.mode_effective.value,
                    lane=record.lane,
                    status=record.status,
                    downgrade_reason=reason.value if reason else None,
                    llm_calls=record.llm_calls,
                    citations=list(record.citations),
                    degraded=list(record.degraded),
                )
                .on_conflict_do_nothing(constraint="uq_thread_turns_turn")
            )
            await session.commit()

    async def recent_turns(self, thread_id: UUID, limit: int) -> list[TurnRecord]:
        async with self._sessions() as session:
            rows = await session.scalars(
                select(ThreadTurnModel)
                .where(ThreadTurnModel.thread_id == thread_id)
                .order_by(ThreadTurnModel.created_at.desc())
                .limit(limit)
            )
            return [_turn(row) for row in rows][::-1]
