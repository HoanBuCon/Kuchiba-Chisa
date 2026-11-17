"""Append-only, hash-chained admin audit log (SEC-ADM-007)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, Identity, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.models.base import Base

ACTOR_LENGTH = 64
TARGET_LENGTH = 128
HASH_LENGTH = 64


class AdminAuditEventModel(Base):
    __tablename__ = "admin_audit_events"
    __table_args__ = (Index("ix_admin_audit_events_created_at", "created_at"),)

    seq: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    actor: Mapped[str] = mapped_column(String(ACTOR_LENGTH), nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    target: Mapped[str] = mapped_column(String(TARGET_LENGTH), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    detail: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    prev_hash: Mapped[str] = mapped_column(String(HASH_LENGTH), nullable=False)
    hash: Mapped[str] = mapped_column(String(HASH_LENGTH), nullable=False, unique=True)
