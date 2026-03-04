from __future__ import annotations

import uuid
import enum
from typing import TYPE_CHECKING
from sqlalchemy import ForeignKey, Text, Integer, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import Index

from app.infrastructure.database.models.base import Base, UUIDMixin, TimestampMixin

if TYPE_CHECKING:
    from app.infrastructure.database.models.user import User
    from app.infrastructure.database.models.conversation import Conversation
    from app.infrastructure.database.models.memory_metadata import MemoryMetadata
    from app.infrastructure.database.models.emotion import AffectionLog

class MessageRole(str, enum.Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"

class Message(Base, UUIDMixin, TimestampMixin):
    """
    Short-Term Memory Layer.
    Holds the literal message history within a Session (Conversation).
    """
    __tablename__ = "messages"

    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    
    role: Mapped[MessageRole] = mapped_column(SQLEnum(MessageRole, name="message_role_enum", create_type=False), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    
    # ── Relationships ─────────────────────────────────────────────────────────
    user: Mapped["User"] = relationship("User", back_populates="messages")
    conversation: Mapped["Conversation"] = relationship("Conversation", back_populates="messages")
    
    # One message might spawn multiple memory pieces
    memory_metadata: Mapped[list["MemoryMetadata"]] = relationship("MemoryMetadata", back_populates="source_message")
    
    # One message might trigger affection changes
    affection_logs: Mapped[list["AffectionLog"]] = relationship("AffectionLog", back_populates="triggered_by_message")

    __table_args__ = (
        Index("ix_messages_created_desc", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<Message id={self.id} role={self.role} tokens={self.token_count}>"
