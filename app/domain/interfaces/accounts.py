"""Ports for the end-user account boundary (no provider SDK leaks into domain)."""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from datetime import datetime

from app.domain.models.account import (
    Account,
    AccountCredentials,
    AuthMethod,
    AuthSessionRecord,
    ExternalProvider,
    VerifiedExternalIdentity,
)


class EmailAlreadyRegisteredError(Exception):
    """Unique-email constraint was hit (also raised on concurrent registration)."""


class ExternalIdentityAlreadyLinkedError(Exception):
    """The provider subject, or this provider for this account, is already linked."""


class IAccountRepository(ABC):
    @abstractmethod
    async def get_by_id(self, account_id: uuid.UUID) -> Account | None: ...

    @abstractmethod
    async def get_credentials_by_email(self, email: str) -> AccountCredentials | None: ...

    @abstractmethod
    async def email_exists(self, email: str) -> bool: ...

    @abstractmethod
    async def get_by_external_identity(
        self, provider: ExternalProvider, subject: str
    ) -> Account | None: ...

    @abstractmethod
    async def create_password_account(self, email: str, password_hash: str) -> Account: ...

    @abstractmethod
    async def create_external_account(self, identity: VerifiedExternalIdentity) -> Account: ...

    @abstractmethod
    async def link_external_identity(
        self, account_id: uuid.UUID, identity: VerifiedExternalIdentity
    ) -> Account: ...

    @abstractmethod
    async def update_password_hash(self, account_id: uuid.UUID, password_hash: str) -> None: ...

    @abstractmethod
    async def create_session(
        self,
        account_id: uuid.UUID,
        token_hash: str,
        expires_at: datetime,
        auth_method: AuthMethod,
    ) -> AuthSessionRecord: ...

    @abstractmethod
    async def get_session_by_token_hash(self, token_hash: str) -> AuthSessionRecord | None: ...

    @abstractmethod
    async def rotate_session_token(
        self, session_id: uuid.UUID, old_token_hash: str, new_token_hash: str, now: datetime
    ) -> bool:
        """Atomically replace the refresh hash; False if it was already rotated/revoked."""

    @abstractmethod
    async def revoke_session(self, session_id: uuid.UUID, now: datetime) -> None: ...


class IPasswordHasher(ABC):
    @abstractmethod
    def hash(self, password: str) -> str: ...

    @abstractmethod
    def verify(self, password: str, password_hash: str) -> bool: ...

    @abstractmethod
    def needs_rehash(self, password_hash: str) -> bool: ...


class IAccountTokenIssuer(ABC):
    @abstractmethod
    def issue_account_access_token(
        self, account_id: uuid.UUID, session_id: uuid.UUID
    ) -> tuple[str, int]:
        """Return (signed access token, lifetime in seconds)."""


class IExternalIdentityProvider(ABC):
    """An OIDC provider adapter. Implementations verify everything server-side."""

    @property
    @abstractmethod
    def provider(self) -> ExternalProvider: ...

    @abstractmethod
    def authorization_url(self, *, state: str, nonce: str, code_challenge: str) -> str: ...

    @abstractmethod
    async def exchange_code(
        self, *, code: str, code_verifier: str, nonce: str
    ) -> VerifiedExternalIdentity:
        """Redeem an authorization code and return the *verified* ID-token identity."""
