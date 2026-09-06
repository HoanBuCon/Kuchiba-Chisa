"""Full-source selection policy for immutable versioned corpus builds."""

from __future__ import annotations

from collections.abc import AsyncIterator

from app.domain.entities.wiki import WikiPage
from app.domain.interfaces.wiki_source import IWikiSource
from app.domain.interfaces.wiki_sync import IWikiSyncStateRepository


class AllPagesSyncStrategy:
    """Yield every source page so a new physical collection is complete.

    Revision state remains an auditable download receipt, but it must not turn a
    full-version build into a delta-only collection. Incremental publication
    requires an independently verified complete base snapshot and is not the
    policy used by the canonical ``run-dag`` command.
    """

    async def enumerate_pages_to_sync(
        self,
        source: IWikiSource,
        sync_state_repository: IWikiSyncStateRepository,
    ) -> AsyncIterator[WikiPage]:
        del sync_state_repository
        async for page in source.get_all_pages():
            yield page
