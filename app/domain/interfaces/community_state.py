"""Port for versioned guild/channel shared state."""

from __future__ import annotations

from typing import Protocol

from app.domain.models.community_state import (
    CommunityMutationResult,
    CommunityStateSnapshot,
    CommunityTurn,
)


class ICommunityStateStore(Protocol):
    async def apply_turn(
        self, *, guild_id: str, channel_id: str, turn: CommunityTurn
    ) -> CommunityMutationResult:
        """Apply one idempotent guild/channel mutation atomically."""
        ...

    async def snapshot(
        self, *, guild_id: str, channel_id: str
    ) -> CommunityStateSnapshot:
        """Return one consistent channel snapshot for summary generation."""
        ...

    async def publish_summary(
        self,
        *,
        guild_id: str,
        channel_id: str,
        source_revision: int,
        summary: str,
    ) -> bool:
        """Publish only if source_revision is newer than the active summary."""
        ...
