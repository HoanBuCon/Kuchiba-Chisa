"""Ports for durable privacy settings and revocation audit records."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Protocol

from app.domain.models.privacy import MemoryPrivacyPolicy


class IPrivacyPreferenceRepository(Protocol):
    async def get_memory_policy(self, user_id: uuid.UUID) -> MemoryPrivacyPolicy:
        """Return deny-by-default policy when the user has no preference record."""
        ...

    async def set_memory_policy(
        self,
        user_id: uuid.UUID,
        *,
        enabled: bool,
        retention_days: int | None,
        changed_at: datetime,
    ) -> MemoryPrivacyPolicy:
        """Persist a policy transition and append a non-content audit record."""
        ...
