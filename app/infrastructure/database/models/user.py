from __future__ import annotations

from typing import TYPE_CHECKING
from sqlalchemy import String, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database.models.base import Base, UUIDMixin, TimestampMixin

if TYPE_CHECKING:
    from app.infrastructure.database.models.conversation import Conversation
    from app.infrastructure.database.models.emotion_state import EmotionState
    from app.infrastructure.database.models.user_stats import UserStats
    from app.infrastructure.database.models.memory_metadata import MemoryMetadata
    from app.infrastructure.database.models.message import Message


class User(Base, UUIDMixin, TimestampMixin):
    """
    Core User entity. Base of all interactions.
    Future-proofed with is_active flag and discord_id support.
    """
    __tablename__ = "users"

    discord_id: Mapped[str | None] = mapped_column(String, unique=True, index=True, nullable=True)
    username: Mapped[str] = mapped_column(String, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    
    # ── Relationships ─────────────────────────────────────────────────────────
    conversations: Mapped[list["Conversation"]] = relationship(
        "Conversation", back_populates="user", cascade="all, delete-orphan"
    )
    messages: Mapped[list["Message"]] = relationship(
        "Message", back_populates="user", cascade="all, delete-orphan"
    )
    memory_metadata: Mapped[list["MemoryMetadata"]] = relationship(
        "MemoryMetadata", back_populates="user", cascade="all, delete-orphan"
    )
    emotion_state: Mapped["EmotionState"] = relationship(
        "EmotionState", cascade="all, delete", uselist=False
    )
    user_stats: Mapped["UserStats"] = relationship(
        "UserStats", cascade="all, delete", uselist=False
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} username={self.username} active={self.is_active}>"
