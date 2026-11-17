"""Role assignments with an audit trail of who granted and revoked them (IAM-001)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.infrastructure.database.models.base import Base

ACTOR_LENGTH = 64


class RoleAssignmentModel(Base):
    __tablename__ = "role_assignments"
    __table_args__ = (
        CheckConstraint("role IN ('chia_con', 'admin')", name="role"),
        CheckConstraint("length(btrim(reason)) > 0", name="reason_not_blank"),
        Index("ix_role_assignments_account", "account_id"),
        # One live assignment per account and role; history rows are revoked ones.
        Index(
            "uq_role_assignments_live",
            "account_id",
            "role",
            unique=True,
            postgresql_where=text("revoked_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    # An account ID, or a system actor such as "system:expiry".
    granted_by: Mapped[str] = mapped_column(String(ACTOR_LENGTH), nullable=False)
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_by: Mapped[str | None] = mapped_column(String(ACTOR_LENGTH), nullable=True)
    revoke_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
