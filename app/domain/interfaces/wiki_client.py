from abc import ABC, abstractmethod
from typing import AsyncGenerator
from app.domain.entities.wiki import WikiPage, WikiRevision

class IWikiClient(ABC):
    """
    Abstracts interaction with the MediaWiki API.
    """
    
    @abstractmethod
    async def get_all_pages(self) -> AsyncGenerator[WikiPage, None]:
        """
        Yields basic metadata (page_id, title, latest_revision_id) for all pages in the Wiki.
        """
        pass
        
    @abstractmethod
    async def download_page(self, page_id: int) -> WikiRevision:
        """
        Downloads the raw wikitext content for a specific page.
        """
        pass
