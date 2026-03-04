from __future__ import annotations

import uuid
import enum
from typing import TYPE_CHECKING
from sqlalchemy import ForeignKey, Integer, String, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import Index

from app.infrastructure.database.models.base import Base, UUIDMixin, TimestampMixin

if TYPE_CHECKING:
    from app.infrastructure.database.models.user import User
    from app.infrastructure.database.models.message import Message


class Mood(str, enum.Enum):
    NEUTRAL = "neutral"
    HAPPY = "happy"
    SHY = "shy"
    JEALOUS = "jealous"
    SAD = "sad"
    EXCITED = "excited"


class EmotionalState(Base, TimestampMixin):
    """
    Current deterministic emotional snapshot per user.
    There is strictly only ONE row per User.
    """
    __tablename__ = "emotional_states"

    # User ID acts as the Primary Key for 1:1 relationship guarantee
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    
    affection_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    mood: Mapped[Mood] = mapped_column(SQLEnum(Mood, name="mood_enum", create_type=False), default=Mood.NEUTRAL, nullable=False)
    
    trust_level: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    attachment_level: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    # ── Relationships ─────────────────────────────────────────────────────────
    user: Mapped["User"] = relationship("User", back_populates="emotional_state")

    def __repr__(self) -> str:
        return f"<EmotionalState user_id={self.user_id} affection={self.affection_score} mood={self.mood}>"


class AffectionLog(Base, UUIDMixin, TimestampMixin):
    """
    Historical audit trail of affection deltas.
    Used for analytical progression and memory decay triggers.
    """
    __tablename__ = "affection_logs"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    triggered_by_message_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("messages.id", ondelete="SET NULL"), nullable=True)
    
    delta: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str | None] = mapped_column(String, nullable=True)
    
    # ── Relationships ─────────────────────────────────────────────────────────
    user: Mapped["User"] = relationship("User", back_populates="affection_logs")
    triggered_by_message: Mapped["Message"] = relationship("Message", back_populates="affection_logs")

    __table_args__ = (
        Index("ix_affection_logs_created_desc", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<AffectionLog id={self.id} delta={self.delta:+d} reason='{self.reason}'>"
