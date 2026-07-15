from __future__ import annotations
import uuid
import enum
from datetime import datetime
from typing import TYPE_CHECKING
from sqlalchemy import ForeignKey, Float, Integer, Boolean, DateTime, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import Index

from app.infrastructure.database.models.base import Base, UUIDMixin, TimestampMixin

if TYPE_CHECKING:
    from app.infrastructure.database.models.user import User
    from app.infrastructure.database.models.message import Message


class MemoryType(str, enum.Enum):
    FACT = "fact"
    EMOTIONAL = "emotional"
    EPISODIC = "episodic"
    SUMMARY = "summary"


class MemoryMetadata(Base, UUIDMixin, TimestampMixin):
    """
    Long-Term Memory Metadata Layer.
    CRITICAL: The `id` primary key directly maps 1:1 to the Qdrant point UUID.
    PostgreSQL handles Hybrid Search filtering (by importance, access count), Qdrant handles semantic similarity.
    """
    __tablename__ = "memory_metadata"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    # The moment of context where this memory was generated
    source_message_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("messages.id", ondelete="SET NULL"), nullable=True)
    
    memory_type: Mapped[MemoryType] = mapped_column(SQLEnum(MemoryType, name="memory_type_enum", create_type=False), nullable=False, index=True)
    
    # Hybrid ranking mechanics
    importance_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    emotional_intensity: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    
    # Pruning mechanics via Decay Algorithm
    last_accessed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    access_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # ── Relationships ─────────────────────────────────────────────────────────
    user: Mapped["User"] = relationship("User", back_populates="memory_metadata")
    source_message: Mapped["Message"] = relationship("Message", back_populates="memory_metadata")

    __table_args__ = (
        Index("ix_memory_type_importance", "memory_type", "importance_score"),
        Index("ix_memory_created_desc", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<MemoryMetadata id={self.id} type={self.memory_type} importance={self.importance_score}>"
