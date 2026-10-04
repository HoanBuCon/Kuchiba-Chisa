"""Test-only in-memory account repository and helpers (no account is ever seeded)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from app.application.security.accounts import AccountAuthService
from app.domain.interfaces.accounts import (
    EmailAlreadyRegisteredError,
    ExternalIdentityAlreadyLinkedError,
    IAccountRepository,
)
from app.domain.models.account import (
    Account,
    AccountCredentials,
    AuthMethod,
    AuthSessionRecord,
    ExternalProvider,
    VerifiedExternalIdentity,
)
from app.infrastructure.security.jwt_authenticator import jwt_authenticator
from app.infrastructure.security.password_hasher import BcryptPasswordHasher


@dataclass
class _Row:
    id: uuid.UUID
    email: str | None
    email_verified: bool
    password_hash: str | None
    is_active: bool = True


@dataclass
class InMemoryAccountRepository(IAccountRepository):
    accounts: dict[uuid.UUID, _Row] = field(default_factory=dict)
    identities: dict[tuple[str, str], uuid.UUID] = field(default_factory=dict)
    sessions: dict[uuid.UUID, dict] = field(default_factory=dict)

    def _account(self, row: _Row) -> Account:
        providers = tuple(
            sorted(p for (p, _), owner in self.identities.items() if owner == row.id)
        )
        return Account(
            id=row.id,
            email=row.email,
            email_verified=row.email_verified,
            has_password=row.password_hash is not None,
            linked_providers=providers,  # type: ignore[arg-type]
            is_active=row.is_active,
        )

    async def get_by_id(self, account_id: uuid.UUID) -> Account | None:
        row = self.accounts.get(account_id)
        return self._account(row) if row else None

    async def get_credentials_by_email(self, email: str) -> AccountCredentials | None:
        for row in self.accounts.values():
            if row.email == email:
                return AccountCredentials(self._account(row), row.password_hash)
        return None

    async def email_exists(self, email: str) -> bool:
        return any(row.email == email for row in self.accounts.values())

    async def get_by_external_identity(
        self, provider: ExternalProvider, subject: str
    ) -> Account | None:
        owner = self.identities.get((provider, subject))
        return await self.get_by_id(owner) if owner else None

    async def create_password_account(self, email: str, password_hash: str) -> Account:
        if await self.email_exists(email):
            raise EmailAlreadyRegisteredError
        row = _Row(uuid.uuid4(), email, False, password_hash)
        self.accounts[row.id] = row
        return self._account(row)

    async def create_external_account(self, identity: VerifiedExternalIdentity) -> Account:
        if identity.email and await self.email_exists(identity.email):
            raise EmailAlreadyRegisteredError
        if (identity.provider, identity.subject) in self.identities:
            raise ExternalIdentityAlreadyLinkedError
        row = _Row(uuid.uuid4(), identity.email, identity.email_verified, None)
        self.accounts[row.id] = row
        self.identities[(identity.provider, identity.subject)] = row.id
        return self._account(row)

    async def link_external_identity(
        self, account_id: uuid.UUID, identity: VerifiedExternalIdentity
    ) -> Account:
        key = (identity.provider, identity.subject)
        already = any(
            owner == account_id and provider == identity.provider
            for (provider, _), owner in self.identities.items()
        )
        if key in self.identities or already:
            raise ExternalIdentityAlreadyLinkedError
        self.identities[key] = account_id
        return self._account(self.accounts[account_id])

    async def update_password_hash(self, account_id: uuid.UUID, password_hash: str) -> None:
        self.accounts[account_id].password_hash = password_hash

    async def create_session(
        self,
        account_id: uuid.UUID,
        token_hash: str,
        expires_at: datetime,
        auth_method: AuthMethod,
    ) -> AuthSessionRecord:
        session_id = uuid.uuid4()
        self.sessions[session_id] = {
            "account_id": account_id,
            "token_hash": token_hash,
            "expires_at": expires_at,
            "revoked_at": None,
            "auth_method": auth_method,
        }
        return self._record(session_id)

    def _record(self, session_id: uuid.UUID) -> AuthSessionRecord:
        data = self.sessions[session_id]
        return AuthSessionRecord(
            id=session_id,
            account_id=data["account_id"],
            expires_at=data["expires_at"],
            revoked_at=data["revoked_at"],
            auth_method=data["auth_method"],
        )

    async def get_session_by_token_hash(self, token_hash: str) -> AuthSessionRecord | None:
        for session_id, data in self.sessions.items():
            if data["token_hash"] == token_hash:
                return self._record(session_id)
        return None

    async def rotate_session_token(
        self, session_id: uuid.UUID, old_token_hash: str, new_token_hash: str, now: datetime
    ) -> bool:
        data = self.sessions.get(session_id)
        if not data or data["token_hash"] != old_token_hash or data["revoked_at"] is not None:
            return False
        data["token_hash"] = new_token_hash
        return True

    async def revoke_session(self, session_id: uuid.UUID, now: datetime) -> None:
        if self.sessions[session_id]["revoked_at"] is None:
            self.sessions[session_id]["revoked_at"] = now


class FakeDbSession:
    """Stands in for AsyncSession in route tests; the repository is in-memory."""

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **delta: float) -> None:
        self.now += timedelta(**delta)


def make_service(
    repo: InMemoryAccountRepository, clock: Clock | None = None
) -> AccountAuthService:
    return AccountAuthService(
        repo_factory=lambda _session: repo,
        password_hasher=BcryptPasswordHasher(rounds=10),
        token_issuer=jwt_authenticator,
        refresh_ttl=timedelta(days=7),
        clock=clock or Clock(),
    )
