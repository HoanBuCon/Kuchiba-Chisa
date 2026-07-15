from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.engine import get_db_session
from app.infrastructure.wiki.mediawiki_client import MediaWikiClient
from app.infrastructure.database.repositories.postgres_wiki_sync import PostgresWikiSyncRepository
from app.infrastructure.storage.filesystem_storage import FilesystemStorage
from app.application.services.wiki_sync_service import WikiSyncService

router = APIRouter(prefix="/admin/ingestion", tags=["Admin Ingestion"])

async def get_wiki_sync_service(session: AsyncSession = Depends(get_db_session)) -> WikiSyncService:
    wiki_client = MediaWikiClient()
    sync_repo = PostgresWikiSyncRepository(session)
    raw_storage = FilesystemStorage()
    return WikiSyncService(wiki_client, sync_repo, raw_storage)

@router.post("/sync")
async def trigger_wiki_sync(
    background_tasks: BackgroundTasks,
    limit: int = 0,
    service: WikiSyncService = Depends(get_wiki_sync_service)
):
    """
    Triggers a full Wiki Sync. 
    Downloads updated pages and dispatches them to Celery.
    If limit is > 0, it restricts the number of pages to sync (useful for testing).
    """
    # For production, you might want to run the actual sync_repo checks in the background 
    # if it takes too long. But get_all_pages() returns an async generator so we can run it.
    # To prevent blocking the API response, we'll run it in a background task.
    
    async def run_sync_task(svc: WikiSyncService, l: int):
        await svc.run_full_sync(limit=l if l > 0 else None)
        
    background_tasks.add_task(run_sync_task, service, limit)
    
    return {"message": "Wiki sync started in background."}
