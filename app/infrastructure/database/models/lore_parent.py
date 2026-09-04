import uuid
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import TEXT, UUID

from app.infrastructure.database.models.base import Base, TimestampMixin, UUIDMixin
from app.domain.entities.lore import LoreParent

class LoreParentModel(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "lore_parents"

    page_id: Mapped[int] = mapped_column(nullable=False, index=True)
    page_title: Mapped[str] = mapped_column(nullable=False, index=True)
    heading: Mapped[str] = mapped_column(nullable=True)
    markdown: Mapped[str] = mapped_column(TEXT, nullable=False)
    source_file: Mapped[str] = mapped_column(nullable=True)
    revision_id: Mapped[int] = mapped_column(nullable=False)
    section_id: Mapped[str] = mapped_column(nullable=True, index=True)
    heading_path: Mapped[str] = mapped_column(nullable=True)
    section_depth: Mapped[int] = mapped_column(nullable=True)

    def to_domain(self) -> LoreParent:
        return LoreParent(
            id=self.id,
            page_id=self.page_id,
            page_title=self.page_title,
            heading=self.heading,
            markdown=self.markdown,
            source_file=self.source_file,
            revision_id=self.revision_id,
            section_id=self.section_id,
            heading_path=self.heading_path,
            section_depth=self.section_depth,
            created_at=self.created_at,
            updated_at=self.updated_at
        )

    @classmethod
    def from_domain(cls, entity: LoreParent) -> "LoreParentModel":
        model = cls(
            id=entity.id,
            page_id=entity.page_id,
            page_title=entity.page_title,
            heading=entity.heading,
            markdown=entity.markdown,
            source_file=entity.source_file,
            revision_id=entity.revision_id,
            section_id=entity.section_id,
            heading_path=entity.heading_path,
            section_depth=entity.section_depth,
        )
        if entity.created_at is not None:
            model.created_at = entity.created_at
        if entity.updated_at is not None:
            model.updated_at = entity.updated_at
        return model
