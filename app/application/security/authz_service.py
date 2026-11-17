"""Server-side authority: permissions, stale-token detection, role changes (IAM-002/003)."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from app.domain.interfaces.authz import IAuthzRepository, IAuthzSnapshotCache, IRoleAuditSink
from app.domain.models.rbac import (
    EXPIRY_ACTOR,
    AccountAuthzState,
    AccountSummary,
    AuthzSnapshot,
    GrantRejection,
    Permission,
    Role,
    RoleAssignment,
    RoleAuditAction,
    RoleAuditEvent,
    effective_permissions,
    grant_rejection,
)

SUPERSEDED_REASON = "superseded"
EXPIRED_REASON = "expired"


class StaleAuthzVersionError(Exception):
    """The token was minted before the account's authority last changed."""


class AccountNotFoundError(LookupError):
    """No account has this ID."""


class RoleChangeRejectedError(ValueError):
    """The grant or revoke request is not acceptable (missing reason, bad expiry)."""


class GrantIneligibleError(Exception):
    """The target account does not meet the grant conditions (ROLE-003)."""

    def __init__(self, rejection: GrantRejection) -> None:
        super().__init__(rejection.value)
        self.rejection = rejection


class AuthzService:
    def __init__(
        self,
        *,
        repo_factory: Callable[[Any], IAuthzRepository],
        cache: IAuthzSnapshotCache,
        audit: IRoleAuditSink,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._repo_factory = repo_factory
        self._cache = cache
        self._audit = audit
        self._clock = clock

    async def permissions_for_token(
        self, session: Any, account_id: uuid.UUID, token_authz_ver: int | None
    ) -> frozenset[Permission]:
        """Permissions come from the database; the token only proves it is not out of date."""
        snapshot = await self._snapshot(session, account_id)
        if token_authz_ver != snapshot.authz_ver:
            raise StaleAuthzVersionError
        return snapshot.permissions

    async def grant_chia_con(
        self,
        session: Any,
        *,
        account_id: uuid.UUID,
        granted_by: str,
        reason: str,
        expires_at: datetime | None = None,
    ) -> None:
        reason = self._required_reason(reason)
        now = self._clock()
        if expires_at is not None and expires_at <= now:
            raise RoleChangeRejectedError("expiry is in the past")
        repo = self._repo_factory(session)
        summary = await self._require_summary(repo, account_id)
        # TODO(ROLE-004): the API layer must demand a fresh step-up MFA before this call.
        rejection = grant_rejection(summary)
        if rejection is not None:
            raise GrantIneligibleError(rejection)
        # A re-grant replaces the live assignment, so there is one per account and role.
        await repo.revoke_active(account_id, Role.CHIA_CON, granted_by, SUPERSEDED_REASON, now)
        await repo.add_assignment(
            RoleAssignment(
                account_id=account_id,
                role=Role.CHIA_CON,
                granted_by=granted_by,
                granted_at=now,
                reason=reason,
                expires_at=expires_at,
            )
        )
        authz_ver = await self._publish_change(repo, account_id)
        await self._audit.record(
            RoleAuditEvent(
                RoleAuditAction.GRANT,
                granted_by,
                account_id,
                Role.CHIA_CON,
                reason,
                now,
                expires_at,
                authz_ver,
            )
        )

    async def account_summary(self, session: Any, account_id: uuid.UUID) -> AccountSummary:
        return await self._require_summary(self._repo_factory(session), account_id)

    async def expire_assignments(self, session: Any) -> int:
        """Revoke assignments past their expiry as `system:expiry` (ROLE-006)."""
        repo = self._repo_factory(session)
        now = self._clock()
        expired = await repo.revoke_expired(EXPIRY_ACTOR, EXPIRED_REASON, now)
        for account_id, role in expired:
            authz_ver = await self._publish_change(repo, account_id)
            await self._audit.record(
                RoleAuditEvent(
                    RoleAuditAction.EXPIRE,
                    EXPIRY_ACTOR,
                    account_id,
                    role,
                    EXPIRED_REASON,
                    now,
                    authz_ver_after=authz_ver,
                )
            )
        return len(expired)

    async def revoke_chia_con(
        self, session: Any, *, account_id: uuid.UUID, revoked_by: str, reason: str
    ) -> bool:
        reason = self._required_reason(reason)
        repo = self._repo_factory(session)
        await self._require_account(repo, account_id)
        # TODO(ROLE-004): the API layer must demand a fresh step-up MFA before this call.
        now = self._clock()
        revoked = await repo.revoke_active(account_id, Role.CHIA_CON, revoked_by, reason, now)
        if not revoked:
            return False
        authz_ver = await self._publish_change(repo, account_id)
        await self._audit.record(
            RoleAuditEvent(
                RoleAuditAction.REVOKE,
                revoked_by,
                account_id,
                Role.CHIA_CON,
                reason,
                now,
                authz_ver_after=authz_ver,
            )
        )
        return True

    async def _snapshot(self, session: Any, account_id: uuid.UUID) -> AuthzSnapshot:
        cached = await self._cache.get(account_id)
        if cached is not None:
            return cached
        state = await self._require_account(self._repo_factory(session), account_id)
        snapshot = AuthzSnapshot(
            state.authz_ver, effective_permissions(state.status, state.assignments, self._clock())
        )
        await self._cache.set(account_id, snapshot)
        return snapshot

    async def _publish_change(self, repo: IAuthzRepository, account_id: uuid.UUID) -> int:
        authz_ver = await repo.bump_authz_ver(account_id)
        await self._cache.invalidate(account_id)
        return authz_ver

    @staticmethod
    async def _require_summary(repo: IAuthzRepository, account_id: uuid.UUID) -> AccountSummary:
        summary = await repo.get_summary(account_id)
        if summary is None:
            raise AccountNotFoundError
        return summary

    @staticmethod
    async def _require_account(repo: IAuthzRepository, account_id: uuid.UUID) -> AccountAuthzState:
        state = await repo.get_state(account_id)
        if state is None:
            raise AccountNotFoundError
        return state

    @staticmethod
    def _required_reason(reason: str) -> str:
        cleaned = reason.strip()
        if not cleaned:
            raise RoleChangeRejectedError("a reason is required")
        return cleaned
