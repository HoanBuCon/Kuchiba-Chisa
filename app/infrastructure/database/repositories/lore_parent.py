import uuid
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.domain.entities.lore import LoreParent
from app.domain.interfaces.repositories import ILoreParentRepository
from app.infrastructure.database.models.lore_parent import LoreParentModel

class LoreParentRepository(ILoreParentRepository):
    """
    SQLAlchemy implementation of the ILoreParentRepository.
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_parent(self, parent_id: uuid.UUID) -> Optional[LoreParent]:
        stmt = select(LoreParentModel).where(LoreParentModel.id == parent_id)
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        if model:
            return model.to_domain()
        return None

    async def get_parents_batch(self, parent_ids: List[uuid.UUID]) -> List[LoreParent]:
        if not parent_ids:
            return []
        stmt = select(LoreParentModel).where(LoreParentModel.id.in_(parent_ids))
        result = await self.session.execute(stmt)
        models = result.scalars().all()
        return [m.to_domain() for m in models]

    async def save_parent(self, parent: LoreParent) -> None:
        model = LoreParentModel.from_domain(parent)
        self.session.add(model)
        await self.session.flush()
