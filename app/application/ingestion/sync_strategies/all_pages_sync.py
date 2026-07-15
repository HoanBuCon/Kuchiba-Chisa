from typing import AsyncGenerator
from app.domain.entities.wiki import WikiPage
from app.domain.interfaces.wiki_client import IWikiClient
from app.domain.interfaces.repositories import IWikiSyncRepository
from app.domain.interfaces.sync_strategy import ISyncStrategy
from app.shared.utils.logger import get_logger

log = get_logger(__name__)

class AllPagesSyncStrategy(ISyncStrategy):
    """
    Sync strategy that retrieves all pages from the Wiki and yields those
    that have a newer revision ID than what is stored in the database.
    """
    
    async def enumerate_pages_to_sync(
        self, 
        client: IWikiClient, 
        repo: IWikiSyncRepository
    ) -> AsyncGenerator[WikiPage, None]:
        log.info("Starting AllPagesSync enumeration...")
        
        async for page in client.get_all_pages():
            stored_revision_id = await repo.get_latest_revision_id(page.page_id)
            
            if stored_revision_id is None or page.latest_revision_id > stored_revision_id:
                log.debug("Page requires sync", title=page.title, new_rev=page.latest_revision_id, old_rev=stored_revision_id)
                yield page
            else:
                # Optionally update sync state status to 'UP_TO_DATE' or skip
                pass
