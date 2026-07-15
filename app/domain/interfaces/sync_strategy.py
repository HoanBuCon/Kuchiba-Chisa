from typing import Protocol, AsyncGenerator
from app.domain.entities.wiki import WikiPage
from app.domain.interfaces.wiki_client import IWikiClient
from app.domain.interfaces.repositories import IWikiSyncRepository

class ISyncStrategy(Protocol):
    """
    Strategy for determining which wiki pages need to be synchronized.
    """
    
    async def enumerate_pages_to_sync(
        self, 
        client: IWikiClient, 
        repo: IWikiSyncRepository
    ) -> AsyncGenerator[WikiPage, None]:
        """
        Yields WikiPage entities that require downloading.
        """
        pass
