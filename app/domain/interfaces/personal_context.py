"""What a v2 turn knows about the person: emotion, core memory, recalled memories (S6)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.domain.entities.emotion import EmotionState


@dataclass(frozen=True)
class PersonalContext:
    emotion: EmotionState
    memories: tuple[str, ...] = ()
    degraded: tuple[str, ...] = field(default=())


class IPersonalContext(Protocol):
    async def load(self, owner: str, *, is_guest: bool, question: str) -> PersonalContext:
        """Guests get emotion only: they have no long-term memory (MEM-007)."""
        ...

    async def apply_sentiment(self, owner: str, sentiment: Mapping[str, Any]) -> None:
        """Update RESONA once for a stored turn (EMO-002, EMO-003)."""
        ...


class IPersonalDataPurge(Protocol):
    """Runs in the caller's transaction, so erasure succeeds or fails as one (MEM-008)."""

    async def delete_core_memory(self, owner: str) -> None: ...

    async def delete_threads(self, owner: str) -> None: ...


class ICoreMemoryStore(Protocol):
    async def get(self, owner: str) -> dict[str, Any] | None: ...

    async def put(self, owner: str, content: Mapping[str, Any]) -> None: ...

    async def delete(self, owner: str) -> bool: ...
