"""Full-source incremental selection policy for wiki ingestion."""

from __future__ import annotations

from collections.abc import AsyncIterator

from app.domain.entities.wiki import WikiPage
from app.domain.interfaces.wiki_source import IWikiSource
from app.domain.interfaces.wiki_sync import IWikiSyncStateRepository


class AllPagesSyncStrategy:
    """Yields only pages whose source revision is newer than stored state."""

    async def enumerate_pages_to_sync(
        self,
        source: IWikiSource,
        sync_state_repository: IWikiSyncStateRepository,
    ) -> AsyncIterator[WikiPage]:
        async for page in source.get_all_pages():
            stored_revision_id = await sync_state_repository.get_latest_revision_id(page.page_id)
            if stored_revision_id is None or page.latest_revision_id > stored_revision_id:
                yield page
