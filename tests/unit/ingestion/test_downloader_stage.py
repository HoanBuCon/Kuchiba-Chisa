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

@pytest.mark.asyncio
async def test_downloader_stage(tmp_path):
    client = MockWikiClient()
    repo = MockSyncRepo()
    strategy = MockSyncStrategy()
    
    stage = DownloaderStage(client, repo, strategy)
    
    input_data = DownloaderInput(output_directory=str(tmp_path))
    result = await stage.execute(input_data)
    
    assert len(result.output) == 1
    assert result.output[0].title == "TestPage"
    assert result.output[0].revision_id == 10
    
    # Check if file was written
    file_path = os.path.join(str(tmp_path), "TestPage_1.wiki")
    assert os.path.exists(file_path)
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
    assert content == "== Heading ==\nContent"
