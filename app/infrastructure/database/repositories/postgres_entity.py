from typing import List, Optional
from datetime import datetime
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from app.domain.interfaces.repositories import IEntityRepository, IAliasRepository
from app.infrastructure.database.models.ingestion import EntityModel, AliasModel
from app.shared.utils.logger import get_logger

log = get_logger(__name__)

class PostgresEntityRepository(IEntityRepository, IAliasRepository):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_all_entities(self) -> List[dict]:
        stmt = select(EntityModel).options(selectinload(EntityModel.aliases))
        result = await self.session.execute(stmt)
        entities = result.scalars().all()
        
        return [
            {
                "id": str(e.id),
                "canonical_name": e.canonical_name,
                "entity_type": e.entity_type,
                "aliases": [a.alias for a in e.aliases]
            }
            for e in entities
        ]

    async def get_latest_update_timestamp(self) -> Optional[datetime]:
        stmt = select(func.max(EntityModel.updated_at))
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all_aliases(self) -> List[dict]:
        stmt = select(AliasModel)
        result = await self.session.execute(stmt)
        aliases = result.scalars().all()
        
        return [
            {
                "id": str(a.id),
                "entity_id": str(a.entity_id),
                "alias": a.alias
            }
            for a in aliases
        ]
