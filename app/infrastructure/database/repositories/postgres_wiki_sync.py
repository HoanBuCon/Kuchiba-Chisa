from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.domain.interfaces.repositories import IWikiSyncRepository
from app.infrastructure.database.models.ingestion import WikiSyncStateModel
from app.shared.utils.logger import get_logger

log = get_logger(__name__)

class PostgresWikiSyncRepository(IWikiSyncRepository):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_latest_revision_id(self, page_id: int) -> Optional[int]:
        stmt = select(WikiSyncStateModel.revision_id).where(WikiSyncStateModel.page_id == page_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def update_sync_state(self, page_id: int, title: str, revision_id: int, status: str) -> None:
        stmt = select(WikiSyncStateModel).where(WikiSyncStateModel.page_id == page_id)
        result = await self.session.execute(stmt)
        state = result.scalar_one_or_none()

        if state:
            state.revision_id = revision_id
            state.page_title = title
            state.sync_status = status
        else:
            state = WikiSyncStateModel(
                page_id=page_id,
                page_title=title,
                revision_id=revision_id,
                sync_status=status
            )
            self.session.add(state)
        
        await self.session.commit()
        log.debug("Updated sync state", page_id=page_id, status=status)
