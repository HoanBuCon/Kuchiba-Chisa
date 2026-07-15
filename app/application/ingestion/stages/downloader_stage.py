import time
import uuid
from typing import List, Optional
from pydantic import BaseModel
from app.domain.entities.wiki import DownloadedPage
from app.domain.interfaces.pipeline import IPipelineStage, PipelineResult, PipelineMetrics
from app.domain.interfaces.wiki_client import IWikiClient
from app.domain.interfaces.repositories import IWikiSyncRepository, IPipelineJobRepository
from app.domain.interfaces.sync_strategy import ISyncStrategy
from app.domain.interfaces.storage import IRawStorage
from app.shared.utils.logger import get_logger

log = get_logger(__name__)

class DownloaderInput(BaseModel):
    limit: Optional[int] = None

class DownloaderStage(IPipelineStage[DownloaderInput, List[DownloadedPage]]):
    """
    The first stage of the Wiki Ingestion Pipeline (V2).
    Synchronizes wiki pages using a SyncStrategy and delegates storage to IRawStorage.
    Logs events to IPipelineJobRepository.
    """

    def __init__(
        self,
        wiki_client: IWikiClient,
        sync_repo: IWikiSyncRepository,
        sync_strategy: ISyncStrategy,
        raw_storage: IRawStorage,
        job_repo: IPipelineJobRepository
    ):
        self.wiki_client = wiki_client
        self.sync_repo = sync_repo
        self.sync_strategy = sync_strategy
        self.raw_storage = raw_storage
        self.job_repo = job_repo

    async def execute(self, job_id: uuid.UUID, input_data: DownloaderInput) -> PipelineResult[List[DownloadedPage]]:
        log.info("Starting DownloaderStage", job_id=job_id)
        await self.job_repo.log_event(job_id, "DownloadStart", {"limit": input_data.limit})
        
        start_time = time.perf_counter()
        downloaded_pages: List[DownloadedPage] = []
        items_failed = 0
        items_skipped = 0
        
        try:
            async for page in self.sync_strategy.enumerate_pages_to_sync(self.wiki_client, self.sync_repo):
                if input_data.limit and len(downloaded_pages) >= input_data.limit:
                    log.info("Reached Downloader input limit", limit=input_data.limit)
                    break
                    
                try:
                    await self.sync_repo.update_sync_state(page.page_id, page.title, page.latest_revision_id, "PENDING")
                    
                    # 1. Download
                    revision = await self.wiki_client.download_page(page.page_id)
                    
                    # 2. Store via abstraction
                    file_path = await self.raw_storage.save_raw_page(page.title, page.page_id, revision.content)
                        
                    # 3. Update Sync state
                    await self.sync_repo.update_sync_state(page.page_id, page.title, page.latest_revision_id, "DOWNLOADED")
                    
                    # 4. Log event
                    await self.job_repo.log_event(job_id, "DownloadSuccess", {"page_id": page.page_id, "title": page.title})
                    
                    downloaded_pages.append(
                        DownloadedPage(
                            page_id=page.page_id,
                            title=page.title,
                            revision_id=revision.revision_id,
                            file_path=file_path
                        )
                    )
                    log.info("Successfully downloaded page", title=page.title, page_id=page.page_id)
                    
                except Exception as e:
                    log.error("Failed to download page", page_id=page.page_id, error=str(e))
                    await self.sync_repo.update_sync_state(page.page_id, page.title, page.latest_revision_id, "FAILED")
                    await self.job_repo.log_event(job_id, "DownloadFailed", {"page_id": page.page_id, "error": str(e)})
                    items_failed += 1
                    
        except Exception as e:
            log.error("Sync strategy enumeration failed", error=str(e))
            await self.job_repo.log_event(job_id, "DownloadFatalError", {"error": str(e)})
            raise e

        metrics = PipelineMetrics(
            duration_seconds=time.perf_counter() - start_time,
            items_processed=len(downloaded_pages),
            items_failed=items_failed,
            items_skipped=items_skipped
        )

        await self.job_repo.log_event(job_id, "DownloadComplete", metrics.model_dump())
        return PipelineResult(output=downloaded_pages, metrics=metrics)
