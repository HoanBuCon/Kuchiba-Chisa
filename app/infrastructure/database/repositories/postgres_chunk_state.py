import uuid
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.domain.interfaces.repositories import IChunkStateRepository
from app.infrastructure.database.models.ingestion import ChunkStateModel

class PostgresChunkStateRepository(IChunkStateRepository):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_chunk_state(self, chunk_id: uuid.UUID) -> Optional[dict]:
        stmt = select(ChunkStateModel).where(ChunkStateModel.chunk_id == chunk_id)
        result = await self.session.execute(stmt)
        record = result.scalars().first()
        if record:
            return {
                "chunk_id": record.chunk_id,
                "parent_id": record.parent_id,
                "chunk_hash": record.chunk_hash,
                "embedded": record.embedded
            }
        return None

    async def check_hash_exists(self, chunk_hash: str) -> bool:
        stmt = select(ChunkStateModel.chunk_hash).where(ChunkStateModel.chunk_hash == chunk_hash)
        result = await self.session.execute(stmt)
        return result.first() is not None
