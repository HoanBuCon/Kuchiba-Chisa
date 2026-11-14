"""Port for v2 threads and their turns (CONV-001, CONV-004)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol
from uuid import UUID

from app.domain.models.thread import ChatMode, Thread, TurnRecord


class IThreadStore(Protocol):
    async def create(self, owner: str, channel: str, mode: ChatMode) -> Thread: ...

    async def get_or_create(
        self, thread_id: UUID, owner: str, channel: str, mode: ChatMode
    ) -> Thread:
        """Racing first messages of a channel end up in the same thread."""
        ...

    async def get(self, thread_id: UUID, owner: str) -> Thread | None:
        """A thread of another owner reads as missing, so its existence does not leak."""
        ...

    async def list_for(self, owner: str, limit: int) -> list[Thread]: ...

    async def update(
        self, thread_id: UUID, owner: str, *, title: str | None, mode: ChatMode | None
    ) -> Thread | None: ...

    async def delete(self, thread_id: UUID, owner: str) -> bool: ...

    async def find_turn(self, thread_id: UUID, turn_id: UUID) -> TurnRecord | None: ...

    async def save_turn(self, record: TurnRecord) -> bool:
        """False when a racing retry stored this turn first."""
        ...

    async def recent_turns(self, thread_id: UUID, limit: int) -> list[TurnRecord]:
        """Oldest first, so they read as a conversation."""
        ...


class ITurnCommit(Protocol):
    async def commit(
        self,
        record: TurnRecord,
        owner: str,
        sentiment: Mapping[str, Any],
        *,
        remember: bool = False,
    ) -> bool:
        """One transaction for the turn, its emotion and, if `remember`, its memory job.

        False when a racing retry stored the turn first; then nothing else is written.
        """
        ...


class ITurnLock(Protocol):
    async def acquire(self, thread_id: UUID) -> str | None:
        """A token while this thread has no turn running, else None (MODE-005)."""
        ...

    async def release(self, thread_id: UUID, token: str) -> None: ...
