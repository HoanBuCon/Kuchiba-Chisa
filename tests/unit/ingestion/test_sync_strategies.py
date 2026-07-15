import pytest
from datetime import datetime
from app.domain.entities.wiki import WikiPage
from app.application.ingestion.sync_strategies.all_pages_sync import AllPagesSyncStrategy

class MockWikiClient:
    async def get_all_pages(self):
        yield WikiPage(page_id=1, title="Page1", latest_revision_id=10, last_updated=datetime.utcnow())
        yield WikiPage(page_id=2, title="Page2", latest_revision_id=20, last_updated=datetime.utcnow())

class MockSyncRepo:
    async def get_latest_revision_id(self, page_id: int):
        if page_id == 1:
            return 10 # Up to date
        if page_id == 2:
            return 15 # Out of date

@pytest.mark.asyncio
async def test_all_pages_sync_strategy():
    client = MockWikiClient()
    repo = MockSyncRepo()
    strategy = AllPagesSyncStrategy()
    
    pages_to_sync = []
    async for page in strategy.enumerate_pages_to_sync(client, repo):
        pages_to_sync.append(page)
        
    assert len(pages_to_sync) == 1
    assert pages_to_sync[0].page_id == 2
    assert pages_to_sync[0].latest_revision_id == 20
