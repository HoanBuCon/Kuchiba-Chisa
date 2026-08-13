import pytest
import os
from datetime import datetime
from app.domain.entities.wiki import WikiPage, WikiRevision
from app.application.ingestion.stages.downloader_stage import DownloaderStage, DownloaderInput

class MockWikiClient:
    async def get_all_pages(self):
        yield WikiPage(page_id=1, title="TestPage", latest_revision_id=10, last_updated=datetime.utcnow())
        
    async def download_page(self, page_id: int):
        return WikiRevision(
            page_id=page_id,
            title="TestPage",
            revision_id=10,
            content="== Heading ==\nContent",
            timestamp=datetime.utcnow()
        )

class MockSyncRepo:
    async def get_latest_revision_id(self, page_id: int):
        return 5 # Mock older revision

    async def update_sync_state(self, page_id: int, title: str, revision_id: int, status: str):
        pass

class MockSyncStrategy:
    async def enumerate_pages_to_sync(self, client, repo):
        yield WikiPage(page_id=1, title="TestPage", latest_revision_id=10, last_updated=datetime.utcnow())

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
