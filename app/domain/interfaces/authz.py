"""Ports for role assignments and the short-lived authority cache (IAM-001, IAM-003)."""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from app.domain.models.rbac import (
    AccountAuthzState,
    AccountSummary,
    AuthzSnapshot,
    Role,
    RoleAssignment,
    RoleAuditEvent,
)


class IAuthzRepository(ABC):
    @abstractmethod
    async def get_state(self, account_id: uuid.UUID) -> AccountAuthzState | None: ...

    @abstractmethod
    async def get_account_id_by_identity(self, provider: str, subject: str) -> uuid.UUID | None:
        """Account that linked this external identity, if any (IAM-009)."""

    @abstractmethod
    async def add_assignment(self, assignment: RoleAssignment) -> None: ...

    @abstractmethod
    async def revoke_active(
        self, account_id: uuid.UUID, role: Role, revoked_by: str, reason: str, now: datetime
    ) -> int:
        """Revoke the live assignments of ``role``; return how many were revoked."""

    @abstractmethod
    async def get_summary(self, account_id: uuid.UUID) -> AccountSummary | None: ...

    @abstractmethod
    async def revoke_expired(
        self, revoked_by: str, reason: str, now: datetime
    ) -> list[tuple[uuid.UUID, Role]]:
        """Revoke every live assignment past its expiry; return each affected account and role."""

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


class IRoleAuditSink(ABC):
    @abstractmethod
    async def record(self, session: Any, event: RoleAuditEvent) -> None:
        """Persist the event in the caller's transaction so it commits with the role change."""
