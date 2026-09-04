"""Domain port for a versioned wiki source used by ingestion."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol

from app.domain.entities.wiki import WikiPage, WikiRevision


class IWikiSource(Protocol):
    """Enumerates wiki pages and retrieves a concrete latest revision."""

    def get_all_pages(self) -> AsyncIterator[WikiPage]: ...

    async def download_page(self, page_id: int) -> WikiRevision: ...
