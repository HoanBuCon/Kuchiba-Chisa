"""Port for v2 threads and their turns (CONV-001, CONV-004)."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from app.domain.models.thread import ChatMode, Thread, TurnRecord


class IThreadStore(Protocol):
    async def create(self, owner: str, channel: str, mode: ChatMode) -> Thread: ...

    async def get(self, thread_id: UUID, owner: str) -> Thread | None:
        """A thread of another owner reads as missing, so its existence does not leak."""
        ...

    async def list_for(self, owner: str, limit: int) -> list[Thread]: ...

    async def update(
        self, thread_id: UUID, owner: str, *, title: str | None, mode: ChatMode | None
    ) -> Thread | None: ...

    async def delete(self, thread_id: UUID, owner: str) -> bool: ...

    async def find_turn(self, thread_id: UUID, turn_id: UUID) -> TurnRecord | None: ...

    async def save_turn(self, record: TurnRecord) -> None: ...

    async def recent_turns(self, thread_id: UUID, limit: int) -> list[TurnRecord]:
        """Oldest first, so they read as a conversation."""
        ...
