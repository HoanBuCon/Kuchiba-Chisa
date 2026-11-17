"""In-memory ports for role-assignment tests."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from app.domain.interfaces.authz import IAuthzRepository, IAuthzSnapshotCache, IRoleAuditSink
from app.domain.models.rbac import (
    AccountAuthzState,
    AccountStatus,
    AccountSummary,
    AuthzSnapshot,
    RoleAssignment,
    RoleAuditEvent,
    mask_email,
)

NOW = datetime(2026, 11, 17, 12, 0, tzinfo=UTC)


class FakeRepo(IAuthzRepository):
    def __init__(
        self, status: AccountStatus = AccountStatus.ACTIVE, *, email_verified: bool = True
    ) -> None:
        self.status = status
        self.email_verified = email_verified
        self.providers: tuple[str, ...] = ()
        self.authz_ver = 1
        self.assignments: list[RoleAssignment] = []
        self.known = True

    async def get_state(self, account_id):
        if not self.known:
            return None
        return AccountAuthzState(account_id, self.status, self.authz_ver, tuple(self.assignments))

    async def get_summary(self, account_id):
        if not self.known:
            return None
        return AccountSummary(
            account_id,
            mask_email("senpai@example.com"),
            NOW - timedelta(days=30),
            self.status,
            self.email_verified,
            self.providers,
        )

    async def revoke_expired(self, revoked_by, reason, now):
        expired = []
        for index, item in enumerate(self.assignments):
            if item.revoked_at is None and item.expires_at is not None and item.expires_at <= now:
                self.assignments[index] = _revoked(item, revoked_by, reason, now)
                expired.append((item.account_id, item.role))
        return expired

    async def add_assignment(self, assignment):
        self.assignments.append(assignment)

    async def revoke_active(self, account_id, role, revoked_by, reason, now):
        revoked = 0
        for index, item in enumerate(self.assignments):
            if item.role is role and item.revoked_at is None:
                self.assignments[index] = _revoked(item, revoked_by, reason, now)
                revoked += 1
        return revoked

    async def bump_authz_ver(self, account_id):
        self.authz_ver += 1
        return self.authz_ver


def _fields(item: RoleAssignment) -> dict:
    return {name: getattr(item, name) for name in item.__slots__}


def _revoked(item: RoleAssignment, by: str, reason: str, now: datetime) -> RoleAssignment:
    return RoleAssignment(
        **{**_fields(item), "revoked_at": now, "revoked_by": by, "revoke_reason": reason}
    )


class MemoryCache(IAuthzSnapshotCache):
    def __init__(self) -> None:
        self.items: dict[uuid.UUID, AuthzSnapshot] = {}

    async def get(self, account_id):
        return self.items.get(account_id)

    async def set(self, account_id, snapshot):
        self.items[account_id] = snapshot

    async def invalidate(self, account_id):
        self.items.pop(account_id, None)


class RecordingAudit(IRoleAuditSink):
    def __init__(self) -> None:
        self.events: list[RoleAuditEvent] = []

    async def record(self, event):
        self.events.append(event)
