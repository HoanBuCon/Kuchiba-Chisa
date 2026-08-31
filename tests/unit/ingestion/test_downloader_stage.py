from datetime import datetime

import pytest

from app.application.ingestion.stages.downloader_stage import DownloaderInput, DownloaderStage
from app.domain.entities.wiki import WikiPage, WikiRevision


class MockWikiClient:
    async def get_all_pages(self):
        yield WikiPage(
            page_id=1, title="TestPage", latest_revision_id=10, last_updated=datetime.utcnow()
        )

    async def download_page(self, page_id: int):
        return WikiRevision(
            page_id=page_id,
            title="TestPage",
            revision_id=10,
            content="== Heading ==\nContent",
            timestamp=datetime.utcnow(),
        )


class MockSyncRepo:
    async def get_latest_revision_id(self, page_id: int):
        return 5  # Mock older revision

    async def update_sync_state(self, page_id: int, title: str, revision_id: int, status: str):
        pass


class MockSyncStrategy:
    async def enumerate_pages_to_sync(self, client, repo):
        yield WikiPage(
            page_id=1, title="TestPage", latest_revision_id=10, last_updated=datetime.utcnow()
        )


class MockRawStorage:
    async def save_raw_page(self, title: str, page_id: int, content: str) -> str:
        return f"{title}_{page_id}.wiki"


class MockJobRepo:
    async def log_event(self, job_id, event_type, payload):
        pass


@pytest.mark.asyncio
async def test_downloader_stage(tmp_path):
    client = MockWikiClient()
    repo = MockSyncRepo()
    strategy = MockSyncStrategy()
    raw_storage = MockRawStorage()
    job_repo = MockJobRepo()

    stage = DownloaderStage(client, repo, strategy, raw_storage, job_repo)

    import uuid

    input_data = DownloaderInput(limit=10)
    job_id = uuid.uuid4()
    result = await stage.execute(job_id, input_data)

    assert len(result.output) == 1
    assert result.output[0].title == "TestPage"
    assert result.output[0].revision_id == 10


@pytest.mark.asyncio
async def test_downloader_stage_rejects_revision_for_a_different_page():
    class MismatchedWikiClient(MockWikiClient):
        async def download_page(self, page_id: int):
            return WikiRevision(
                page_id=999,
                title="WrongPage",
                revision_id=10,
                content="Unexpected content",
                timestamp=datetime.utcnow(),
            )

    class TrackingRawStorage(MockRawStorage):
        def __init__(self):
            self.saved_pages = []

        async def save_raw_page(self, title: str, page_id: int, content: str) -> str:
            self.saved_pages.append((title, page_id, content))
            return await super().save_raw_page(title, page_id, content)

    class TrackingSyncRepo(MockSyncRepo):
        def __init__(self):
            self.state_updates = []

        async def update_sync_state(self, page_id: int, title: str, revision_id: int, status: str):
            self.state_updates.append((page_id, title, revision_id, status))

    raw_storage = TrackingRawStorage()
    sync_repository = TrackingSyncRepo()
    stage = DownloaderStage(
        MismatchedWikiClient(),
        sync_repository,
        MockSyncStrategy(),
        raw_storage,
        MockJobRepo(),
    )

    import uuid

    result = await stage.execute(uuid.uuid4(), DownloaderInput(limit=10))

    assert result.output == []
    assert result.metrics.items_failed == 1
    assert raw_storage.saved_pages == []
    assert sync_repository.state_updates == []
