"""v2 threads and turns; separate from legacy messages, which need a users row guests lack."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.models.base import Base, UUIDMixin

OWNER_LENGTH = 255
LABEL_LENGTH = 32


class ThreadModel(Base, UUIDMixin):
    __tablename__ = "threads"

    owner_principal: Mapped[str] = mapped_column(String(OWNER_LENGTH), nullable=False)
    channel: Mapped[str] = mapped_column(String(LABEL_LENGTH), nullable=False)
    mode: Mapped[str] = mapped_column(String(LABEL_LENGTH), nullable=False)
    title: Mapped[str | None] = mapped_column(String(OWNER_LENGTH), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("ix_threads_owner_created", "owner_principal", "created_at"),)


class ThreadTurnModel(Base, UUIDMixin):
    __tablename__ = "thread_turns"

    thread_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("threads.id", ondelete="CASCADE"), nullable=False
    )
    turn_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    mode_requested: Mapped[str] = mapped_column(String(LABEL_LENGTH), nullable=False)
    mode_effective: Mapped[str] = mapped_column(String(LABEL_LENGTH), nullable=False)
    lane: Mapped[str] = mapped_column(String(LABEL_LENGTH), nullable=False)
    status: Mapped[str] = mapped_column(String(LABEL_LENGTH), nullable=False)
    downgrade_reason: Mapped[str | None] = mapped_column(String(LABEL_LENGTH), nullable=True)
    llm_calls: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    citations: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    degraded: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("thread_id", "turn_id", name="uq_thread_turns_turn"),
        Index("ix_thread_turns_thread_created", "thread_id", "created_at"),
    )
