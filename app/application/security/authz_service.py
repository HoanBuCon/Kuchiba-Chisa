"""Server-side authority: permissions, stale-token detection, role changes (IAM-002/003)."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from app.domain.interfaces.authz import IAuthzRepository, IAuthzSnapshotCache
from app.domain.models.rbac import (
    AccountAuthzState,
    AuthzSnapshot,
    Permission,
    Role,
    RoleAssignment,
    effective_permissions,
    guest_permissions,
)

SUPERSEDED_REASON = "superseded"


class StaleAuthzVersionError(Exception):
    """The token was minted before the account's authority last changed."""


class AccountNotFoundError(LookupError):
    """No account has this ID."""


class RoleChangeRejectedError(ValueError):
    """The grant or revoke request is not acceptable (missing reason, bad expiry)."""


class AuthzService:
    def __init__(
        self,
        *,
        repo_factory: Callable[[Any], IAuthzRepository],
        cache: IAuthzSnapshotCache,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._repo_factory = repo_factory
        self._cache = cache
        self._clock = clock

    async def permissions_for_token(
        self, session: Any, account_id: uuid.UUID, token_authz_ver: int | None
    ) -> frozenset[Permission]:
        """Permissions come from the database; the token only proves it is not out of date."""
        snapshot = await self._snapshot(session, account_id)
        if token_authz_ver != snapshot.authz_ver:
            raise StaleAuthzVersionError
        return snapshot.permissions

    async def permissions_for_discord_user(
        self, session: Any, discord_user_id: str
    ) -> frozenset[Permission]:
        """Resolve a bot-supplied Discord user only through a linked identity (IAM-009).

        An unlinked user is a Discord guest; the bot cannot claim any role.
        """
        repo = self._repo_factory(session)
        account_id = await repo.get_account_id_by_identity("discord", discord_user_id)
        if account_id is None:
            return guest_permissions()
        try:
            return (await self._snapshot(session, account_id)).permissions
        except AccountNotFoundError:
            return guest_permissions()

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
        await self._require_account(repo, account_id)
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
        await self._publish_change(repo, account_id)

    async def revoke_chia_con(
        self, session: Any, *, account_id: uuid.UUID, revoked_by: str, reason: str
    ) -> bool:
        reason = self._required_reason(reason)
        repo = self._repo_factory(session)
        await self._require_account(repo, account_id)
        revoked = await repo.revoke_active(
            account_id, Role.CHIA_CON, revoked_by, reason, self._clock()
        )
        if revoked:
            await self._publish_change(repo, account_id)
        return bool(revoked)

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

    async def _publish_change(self, repo: IAuthzRepository, account_id: uuid.UUID) -> None:
        await repo.bump_authz_ver(account_id)
        await self._cache.invalidate(account_id)

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
