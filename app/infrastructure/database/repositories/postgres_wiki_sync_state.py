"""PostgreSQL implementation of the durable MediaWiki revision cursor."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models.ingestion import WikiSyncStateModel


class PostgresWikiSyncStateRepository:
    """Monotonically persist successfully stored source revisions."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_latest_revision_id(self, page_id: int) -> int | None:
        result = await self._session.execute(
            select(WikiSyncStateModel.revision_id).where(WikiSyncStateModel.page_id == page_id)
        )
        return result.scalar_one_or_none()

    async def update_sync_state(
        self, page_id: int, title: str, revision_id: int, status: str
    ) -> None:
        if page_id < 1 or revision_id < 1:
            raise ValueError("page_id and revision_id must be positive")
        if not title.strip() or not status.strip():
            raise ValueError("title and status must not be empty")
        statement = insert(WikiSyncStateModel).values(
            page_id=page_id,
            page_title=title.strip(),
            revision_id=revision_id,
            sync_status=status.strip(),
            last_synced_at=datetime.utcnow(),
        )
        statement = statement.on_conflict_do_update(
            index_elements=[WikiSyncStateModel.page_id],
            set_={
                "page_title": statement.excluded.page_title,
                "revision_id": statement.excluded.revision_id,
                "sync_status": statement.excluded.sync_status,
                "last_synced_at": statement.excluded.last_synced_at,
            },
            where=statement.excluded.revision_id >= WikiSyncStateModel.revision_id,
        )
        await self._session.execute(statement)
        await self._session.commit()
