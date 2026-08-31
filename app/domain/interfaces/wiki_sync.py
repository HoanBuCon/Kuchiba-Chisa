"""Domain port for persisted wiki revision state."""

from __future__ import annotations

from typing import Protocol


class IWikiSyncStateRepository(Protocol):
    """Tracks the latest successfully stored revision for each wiki page."""

    async def get_latest_revision_id(self, page_id: int) -> int | None: ...

    async def update_sync_state(
        self, page_id: int, title: str, revision_id: int, status: str
    ) -> None: ...
