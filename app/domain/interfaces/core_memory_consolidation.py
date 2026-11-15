"""Ports of the core memory consolidation job: the versioned profile and new episodic memories."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class EpisodicMemory:
    id: str
    text: str
    created_at: int


@dataclass(frozen=True)
class ConsolidationState:
    """`version` is None while the person has no core memory row yet."""

    content: dict[str, Any] = field(default_factory=dict)
    version: int | None = None
    consolidated_through: int = 0
    job_owned: dict[str, list[str]] = field(default_factory=dict)
    # Ids already folded in among the memories created exactly at `consolidated_through`.
    boundary_ids: tuple[str, ...] = ()


class IEpisodicMemorySource(Protocol):
    async def list_user_memories_since(
        self, user_id: str, created_at_from: int, limit: int
    ) -> list[EpisodicMemory]:
        """The oldest `limit` memories created at or after the timestamp, oldest first."""
        ...


class ICoreMemoryConsolidationStore(Protocol):
    async def load(self, owner: str) -> ConsolidationState: ...

    async def commit(
        self,
        owner: str,
        *,
        expected_version: int | None,
        content: Mapping[str, Any] | None,
        job_owned: Mapping[str, list[str]],
        consolidated_through: int,
        boundary_ids: tuple[str, ...],
    ) -> bool:
        """Write only if the core memory is still at `expected_version`; False means a lost race.

        `content=None` leaves the profile as it is and only moves the watermark.
        """
        ...
