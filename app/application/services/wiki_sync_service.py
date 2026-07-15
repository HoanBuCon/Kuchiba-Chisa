import asyncio
from typing import Optional

from app.domain.interfaces.wiki_client import IWikiClient
from app.domain.interfaces.repositories import IWikiSyncRepository
from app.domain.interfaces.storage import IRawStorage
from app.domain.entities.wiki import DownloadedPage
from app.infrastructure.tasks.ingestion_tasks import process_page_task
from app.shared.utils.logger import get_logger

log = get_logger(__name__)

class WikiSyncService:
    """
    Coordinates the synchronization between Fandom Wiki and the local DB.
    Dispatches Celery tasks for pages that need updating.
    """

    def __init__(
        self,
        wiki_client: IWikiClient,
        sync_repo: IWikiSyncRepository,
        raw_storage: IRawStorage
    ):
        self.wiki_client = wiki_client
        self.sync_repo = sync_repo
        self.raw_storage = raw_storage

    async def run_full_sync(self, limit: Optional[int] = None) -> int:
        """
        Scans all pages on the wiki.
        Checks against the database for changes (revision_id).
        Dispatches a Celery task for updated/new pages.
        Returns the number of pages dispatched.
        """
        log.info("Starting Wiki Full Sync")
        dispatched_count = 0

        async for wiki_page in self.wiki_client.get_all_pages():
            if limit is not None and dispatched_count >= limit:
                break
                
            needs_update = await self.sync_repo.requires_update(wiki_page.page_id, wiki_page.latest_revision_id)
            if not needs_update:
                log.debug("Page is up to date, skipping", page_id=wiki_page.page_id, title=wiki_page.title)
                continue

            try:
                # 1. Download full content
                revision = await self.wiki_client.download_page(wiki_page.page_id)
                
                # 2. Save raw Markdown/Wikitext to disk
                file_path = await self.raw_storage.save_raw_page(
                    title=revision.title,
                    page_id=revision.page_id,
                    content=revision.content
                )
                
                # 3. Update Sync State in DB to "QUEUED"
                await self.sync_repo.upsert_sync_state(
                    page_id=revision.page_id,
                    title=revision.title,
                    revision_id=revision.revision_id,
                    sync_status="QUEUED"
                )
                
                # 4. Dispatch Celery Task
                # Using Pydantic's model_dump to serialize payload for Celery broker
                downloaded_page = DownloadedPage(
                    page_id=revision.page_id,
                    title=revision.title,
                    revision_id=revision.revision_id,
                    url=f"https://wutheringwaves.fandom.com/wiki/{revision.title.replace(' ', '_')}",
                    file_path=file_path
                )
                
                process_page_task.delay(downloaded_page.model_dump())
                
                dispatched_count += 1
                log.info("Dispatched page to Celery", page_id=revision.page_id, title=revision.title)
                
            except Exception as e:
                log.error("Failed to sync page", page_id=wiki_page.page_id, title=wiki_page.title, error=str(e))
                await self.sync_repo.upsert_sync_state(
                    page_id=wiki_page.page_id,
                    title=wiki_page.title,
                    revision_id=wiki_page.latest_revision_id,
                    sync_status="FAILED"
                )

        log.info("Wiki Full Sync Completed", dispatched_count=dispatched_count)
        return dispatched_count
