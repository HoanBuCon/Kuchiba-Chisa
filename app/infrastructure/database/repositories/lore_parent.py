import hashlib
import uuid
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.lore import LoreParent
from app.domain.interfaces.repositories import ILoreParentRepository
from app.domain.models.corpus_manifest import (
    ParentCorpusManifest,
    ParentManifestRow,
    parent_manifest_checksum,
)
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
        await self.session.merge(model)
        await self.session.flush()

    async def get_corpus_manifest(
        self, *, source_id: uuid.UUID, corpus_version: str
    ) -> ParentCorpusManifest:
        """Read and hash only the exact parent set referenced by one release receipt."""
        result = await self.session.execute(
            select(LoreParentModel).where(
                LoreParentModel.source_id == source_id,
                LoreParentModel.corpus_version == corpus_version,
            )
        )
        rows = [
            ParentManifestRow(
                parent_id=str(model.id),
                content_hash=hashlib.sha256(model.markdown.encode("utf-8")).hexdigest(),
                source_id=str(model.source_id),
                corpus_version=str(model.corpus_version),
                access=model.to_domain().access,
            )
            for model in result.scalars().all()
        ]
        return ParentCorpusManifest(
            parent_count=len(rows),
            checksum=parent_manifest_checksum(rows),
        )
