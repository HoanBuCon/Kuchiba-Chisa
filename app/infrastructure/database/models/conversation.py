from __future__ import annotations
import uuid
from datetime import datetime
from typing import TYPE_CHECKING
from sqlalchemy import ForeignKey, Text, Boolean, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from sqlalchemy import Index

from app.infrastructure.database.models.base import Base, UUIDMixin

if TYPE_CHECKING:
    from app.infrastructure.database.models.user import User
    from app.infrastructure.database.models.message import Message


class Conversation(Base, UUIDMixin):
    """
    Represents one discrete chat session. 
    Crucial for partitioning Short-Term Memory and limiting context windows.
    """
    __tablename__ = "conversations"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # ── Relationships ─────────────────────────────────────────────────────────
    user: Mapped["User"] = relationship("User", back_populates="conversations")
    messages: Mapped[list["Message"]] = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_conversations_user_started", "user_id", "started_at", postgresql_where='started_at IS NOT NULL'),
    )

    def __repr__(self) -> str:
        return f"<Conversation id={self.id} user_id={self.user_id} archived={self.is_archived}>"
