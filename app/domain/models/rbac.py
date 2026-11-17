"""Roles, permissions and the pure computation of effective authority (IAM-001/002/010)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class Role(StrEnum):
    GUEST = "guest"
    MEMBER = "member"
    CHIA_CON = "chia_con"
    ADMIN = "admin"


class Permission(StrEnum):
    CHAT_WRITE = "chat:write"
    CHAT_AGENTIC = "chat:agentic"
    THREAD_MANAGE = "thread:manage"
    MEMORY_LONG_TERM = "memory:long_term"
    ROLE_CHIA_CON_GRANT = "role:chia_con:grant"
    ROLE_CHIA_CON_REVOKE = "role:chia_con:revoke"
    ACCOUNT_READ_METADATA = "account:read_metadata"
    ADMIN_CONSOLE = "admin:console"


class AccountStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    DELETED = "deleted"


# Bump when the role-permission matrix changes so cached snapshots are discarded.
PERMISSIONS_VERSION = 1
# Revocation must take effect within 60 s (IAM-003); a cached snapshot may not outlive half of that.
SNAPSHOT_TTL_SECONDS = 30

_GUEST = frozenset({Permission.CHAT_WRITE})
_MEMBER = _GUEST | {Permission.THREAD_MANAGE, Permission.MEMORY_LONG_TERM}
_CHIA_CON = _MEMBER | {Permission.CHAT_AGENTIC}
_ADMIN = _CHIA_CON | {
    Permission.ROLE_CHIA_CON_GRANT,
    Permission.ROLE_CHIA_CON_REVOKE,
    Permission.ACCOUNT_READ_METADATA,
    Permission.ADMIN_CONSOLE,
}

ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.GUEST: _GUEST,
    Role.MEMBER: _MEMBER,
    Role.CHIA_CON: _CHIA_CON,
    Role.ADMIN: _ADMIN,
}


@dataclass(frozen=True, slots=True)
class RoleAssignment:
    account_id: uuid.UUID
    role: Role
    granted_by: str
    granted_at: datetime
    reason: str
    expires_at: datetime | None = None
    revoked_at: datetime | None = None
    revoked_by: str | None = None
    revoke_reason: str | None = None

    def is_active(self, now: datetime) -> bool:
        if self.revoked_at is not None:
            return False
        return self.expires_at is None or self.expires_at > now


@dataclass(frozen=True, slots=True)
class AccountAuthzState:
    """What the database says about one account's authority."""

    account_id: uuid.UUID
    status: AccountStatus
    authz_ver: int
    assignments: tuple[RoleAssignment, ...] = ()


@dataclass(frozen=True, slots=True)
class AuthzSnapshot:
    """Cacheable result of computing an account's authority."""

    authz_ver: int
    permissions: frozenset[Permission]


class GrantRejection(StrEnum):
    """Why a Chia-con grant is refused (ROLE-003)."""

    ACCOUNT_NOT_ACTIVE = "account_not_active"
    IDENTITY_NOT_VERIFIED = "identity_not_verified"


@dataclass(frozen=True, slots=True)
class AccountSummary:
    """What an Admin sees before confirming a grant (ROLE-002); the e-mail is already masked."""

    account_id: uuid.UUID
    masked_email: str | None
    created_at: datetime
    status: AccountStatus
    email_verified: bool
    linked_providers: tuple[str, ...]

    @property
    def has_verified_identity(self) -> bool:
        # A provider link only exists after the provider's identity assertion was verified.
        return self.email_verified or bool(self.linked_providers)


class RoleAuditAction(StrEnum):
    GRANT = "role.grant"
    REVOKE = "role.revoke"
    EXPIRE = "role.expire"


@dataclass(frozen=True, slots=True)
class RoleAuditEvent:
    """One role change; carries no e-mail or other personal data (SEC-ADM-008)."""

    action: RoleAuditAction
    actor: str
    account_id: uuid.UUID
    role: Role
    reason: str
    at: datetime
    expires_at: datetime | None = None
    authz_ver_after: int | None = None
    request_id: str | None = None


EXPIRY_ACTOR = "system:expiry"


def mask_email(email: str) -> str:
    local, _, domain = email.partition("@")
    return f"{local[:1]}***@{domain}"


def grant_rejection(summary: AccountSummary) -> GrantRejection | None:
    if summary.status is not AccountStatus.ACTIVE:
        return GrantRejection.ACCOUNT_NOT_ACTIVE
    if not summary.has_verified_identity:
        return GrantRejection.IDENTITY_NOT_VERIFIED
    return None


def guest_permissions() -> frozenset[Permission]:
    return ROLE_PERMISSIONS[Role.GUEST]


def effective_permissions(
    status: AccountStatus, assignments: tuple[RoleAssignment, ...], now: datetime
) -> frozenset[Permission]:
    """A registered active account is a member; live assignments add to that (IAM-010)."""
    if status is not AccountStatus.ACTIVE:
        return frozenset()
    granted = set(ROLE_PERMISSIONS[Role.MEMBER])
    for assignment in assignments:
        if assignment.is_active(now):
            granted |= ROLE_PERMISSIONS[assignment.role]
    return frozenset(granted)
