"""SQLAlchemy adapter for consent records; it never stores user content."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.interfaces.privacy import IPrivacyPreferenceRepository
from app.domain.models.privacy import MemoryPrivacyPolicy
from app.infrastructure.database.models.privacy import (
    PrivacyPolicyAuditModel,
    UserPrivacyPreferenceModel,
)


class SqlAlchemyPrivacyPreferenceRepository(IPrivacyPreferenceRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_memory_policy(self, user_id: uuid.UUID) -> MemoryPrivacyPolicy:
        row = await self._session.scalar(
            select(UserPrivacyPreferenceModel).where(UserPrivacyPreferenceModel.user_id == user_id)
        )
        if row is None:
            return MemoryPrivacyPolicy()
        return MemoryPrivacyPolicy(
            long_term_memory_enabled=row.long_term_memory_enabled,
            retention_days=row.retention_days,
            consented_at=row.consented_at,
        )

    async def set_memory_policy(
        self,
        user_id: uuid.UUID,
        *,
        enabled: bool,
        retention_days: int | None,
        changed_at: datetime,
    ) -> MemoryPrivacyPolicy:
        row = await self._session.scalar(
            select(UserPrivacyPreferenceModel).where(UserPrivacyPreferenceModel.user_id == user_id)
        )
        if row is None:
            row = UserPrivacyPreferenceModel(user_id=user_id)
            self._session.add(row)
        row.long_term_memory_enabled = enabled
        row.retention_days = retention_days
        row.consented_at = changed_at if enabled else None
        self._session.add(
            PrivacyPolicyAuditModel(
                user_id=user_id,
                long_term_memory_enabled=enabled,
                retention_days=retention_days,
                occurred_at=changed_at,
            )
        )
        await self._session.flush()
        return MemoryPrivacyPolicy(
            long_term_memory_enabled=enabled,
            retention_days=retention_days,
            consented_at=row.consented_at,
        )
