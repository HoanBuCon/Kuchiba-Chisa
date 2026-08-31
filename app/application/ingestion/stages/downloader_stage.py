"""Download and persist revision-validated wiki pages for ingestion."""

from __future__ import annotations

import time
import uuid
from collections.abc import AsyncIterator
from typing import Protocol

from pydantic import BaseModel, Field

from app.domain.entities.wiki import DownloadedPage, WikiPage
from app.domain.interfaces.pipeline import IPipelineStage, PipelineMetrics, PipelineResult
from app.domain.interfaces.repositories import IPipelineJobRepository
from app.domain.interfaces.storage import IRawStorage
from app.domain.interfaces.wiki_source import IWikiSource
from app.domain.interfaces.wiki_sync import IWikiSyncStateRepository
from app.shared.utils.logger import get_logger

log = get_logger(__name__)


class DownloaderInput(BaseModel):
    """Bounds a single ingestion batch without changing source selection policy."""

    limit: int | None = Field(default=None, ge=1, le=10_000)


class IWikiSyncStrategy(Protocol):
    """Typed application contract for page selection policies."""

    def enumerate_pages_to_sync(
        self,
        source: IWikiSource,
        sync_state_repository: IWikiSyncStateRepository,
    ) -> AsyncIterator[WikiPage]: ...


class DownloaderStage(IPipelineStage[DownloaderInput, list[DownloadedPage]]):
    """Downloads selected pages and persists only revision-consistent content."""

    def __init__(
        self,
        source: IWikiSource,
        sync_state_repository: IWikiSyncStateRepository,
        sync_strategy: IWikiSyncStrategy,
        raw_storage: IRawStorage,
        job_repository: IPipelineJobRepository,
    ) -> None:
        self._source = source
        self._sync_state_repository = sync_state_repository
        self._sync_strategy = sync_strategy
        self._raw_storage = raw_storage
        self._job_repository = job_repository

    async def execute(
        self, job_id: uuid.UUID, input_data: DownloaderInput
    ) -> PipelineResult[list[DownloadedPage]]:
        started_at = time.perf_counter()
        downloaded_pages: list[DownloadedPage] = []
        items_failed = 0
        items_seen = 0

        await self._job_repository.log_event(job_id, "DownloadStart", {"limit": input_data.limit})

        async for page in self._sync_strategy.enumerate_pages_to_sync(
            self._source, self._sync_state_repository
        ):
            if input_data.limit is not None and items_seen >= input_data.limit:
                break
            items_seen += 1

            try:
                revision = await self._source.download_page(page.page_id)
                if revision.page_id != page.page_id:
                    raise ValueError("Downloaded revision page_id does not match the selected page")

                file_path = await self._raw_storage.save_raw_page(
                    revision.title, revision.page_id, revision.content
                )
                await self._sync_state_repository.update_sync_state(
                    page_id=revision.page_id,
                    title=revision.title,
                    revision_id=revision.revision_id,
                    status="downloaded",
                )
                downloaded_pages.append(
                    DownloadedPage(
                        page_id=revision.page_id,
                        title=revision.title,
                        revision_id=revision.revision_id,
                        file_path=file_path,
                    )
                )
                await self._job_repository.log_event(
                    job_id, "DownloadSuccess", {"page_id": revision.page_id}
                )
            except Exception as exc:
                items_failed += 1
                log.warning(
                    "Wiki page download failed",
                    page_id=page.page_id,
                    error_type=type(exc).__name__,
                )
                await self._job_repository.log_event(
                    job_id,
                    "DownloadFailed",
                    {"page_id": page.page_id, "error_type": type(exc).__name__},
                )

        metrics = PipelineMetrics(
            duration_seconds=time.perf_counter() - started_at,
            items_processed=len(downloaded_pages),
            items_failed=items_failed,
            items_skipped=0,
        )
        await self._job_repository.log_event(job_id, "DownloadComplete", metrics.model_dump())
        return PipelineResult(output=downloaded_pages, metrics=metrics)
