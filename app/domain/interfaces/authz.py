"""Ports for role assignments and the short-lived authority cache (IAM-001, IAM-003)."""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from datetime import datetime

from app.domain.models.rbac import AccountAuthzState, AuthzSnapshot, Role, RoleAssignment


class IAuthzRepository(ABC):
    @abstractmethod
    async def get_state(self, account_id: uuid.UUID) -> AccountAuthzState | None: ...

    @abstractmethod
    async def add_assignment(self, assignment: RoleAssignment) -> None: ...

    @abstractmethod
    async def revoke_active(
        self, account_id: uuid.UUID, role: Role, revoked_by: str, reason: str, now: datetime
    ) -> int:
        """Revoke the live assignments of ``role``; return how many were revoked."""

    @abstractmethod
    async def bump_authz_ver(self, account_id: uuid.UUID) -> int:
        """Atomically increment and return the account's authorization version."""


class IAuthzSnapshotCache(ABC):
    @abstractmethod
    async def get(self, account_id: uuid.UUID) -> AuthzSnapshot | None: ...

    @abstractmethod
    async def set(self, account_id: uuid.UUID, snapshot: AuthzSnapshot) -> None: ...

    @abstractmethod
    async def invalidate(self, account_id: uuid.UUID) -> None: ...
