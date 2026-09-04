"""Durable, non-content privacy preferences and immutable transition audit."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.models.base import Base, TimestampMixin


class UserPrivacyPreferenceModel(Base, TimestampMixin):
    __tablename__ = "user_privacy_preferences"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    long_term_memory_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    retention_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    consented_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PrivacyPolicyAuditModel(Base):
    __tablename__ = "privacy_policy_audit_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    long_term_memory_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    retention_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
