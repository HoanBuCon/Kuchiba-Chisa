"""Account registration, sign-in, refresh-session and external-identity policy.

Security properties enforced here (independent of HTTP/provider details):

* the principal subject of an account session is the server-owned account ID;
  no client-supplied identifier is ever accepted;
* passwords are only handled through ``IPasswordHasher``; unknown e-mails still
  pay one hash verification so response timing does not reveal registration;
* refresh secrets are random 256-bit values stored only as SHA-256 hashes and are
  rotated on every refresh; logout revokes the server-side session;
* an external identity is keyed by provider + stable subject. A matching e-mail
  is *never* sufficient to attach it to an existing account (no silent merge, no
  takeover through e-mail collision). Linking requires an already authenticated
  account session;
* password accounts must prove e-mail ownership before they can sign in.
  Registration never reveals whether an address is taken: every outcome is an
  e-mail to that address (verification, "you already have an account" reset
  link, or a claim link for an address held by an unverified account);
* e-mailed secrets (verification, reset) are random 256-bit values stored only
  as SHA-256, single-use, short-lived, and rate-limited per account. A password
  reset proves ownership of the address: it replaces the password, marks the
  e-mail verified and revokes every refresh session (this is how a squatted,
  unverified address is reclaimed).
"""

from __future__ import annotations

import asyncio
import hashlib
import secrets
import uuid
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta

from app.domain.interfaces.accounts import (
    EmailAlreadyRegisteredError,
    ExternalIdentityAlreadyLinkedError,
    IAccountRepository,
    IAccountTokenIssuer,
    IPasswordHasher,
)
from app.domain.interfaces.session import IDbSession
from app.domain.models.account import (
    Account,
    AccountPolicyError,
    AccountTokenPurpose,
    AuthMethod,
    AuthSessionRecord,
    IssuedAccountSession,
    OutboundAccountEmail,
    VerifiedExternalIdentity,
    normalize_email,
    validate_new_password,
)


class InvalidCredentialsError(Exception):
    """E-mail/password pair rejected. Deliberately carries no reason."""


class SessionInvalidError(Exception):
    """Refresh session missing, expired, revoked or already rotated."""


class AccountLinkRequiredError(Exception):
    """External identity is new but its e-mail belongs to an existing account."""


class EmailClaimRequiredError(Exception):
    """External identity's verified e-mail is held by an *unverified* password account.

    The owner reclaims it with "forgot password" (a reset link to the address),
    then links the external identity; accounts are never merged automatically.
    """


class EmailNotVerifiedError(Exception):
    """Correct password, but the account has not verified its e-mail yet."""


class AccountTokenInvalidError(Exception):
    """Verification/reset token unknown, expired, already used or wrong purpose."""


class ExternalIdentityRejectedError(Exception):
    """External identity cannot be used (unverified e-mail or conflicting link)."""


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# E-mailed secrets use the same one-way hash as refresh secrets.
hash_account_token = hash_refresh_token
_MAX_TOKEN_CHARS = 256


class AccountAuthService:
    def __init__(
        self,
        *,
        repo_factory: Callable[[IDbSession], IAccountRepository],
        password_hasher: IPasswordHasher,
        token_issuer: IAccountTokenIssuer,
        refresh_ttl: timedelta,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        verification_ttl: timedelta = timedelta(hours=24),
        reset_ttl: timedelta = timedelta(minutes=30),
        email_cooldown: timedelta = timedelta(seconds=60),
        email_daily_limit: int = 5,
    ) -> None:
        self._repo_factory = repo_factory
        self._hasher = password_hasher
        self._tokens = token_issuer
        self._refresh_ttl = refresh_ttl
        self._clock = clock
        self._dummy_hash: str | None = None
        self._token_ttl: dict[AccountTokenPurpose, timedelta] = {
            "verify_email": verification_ttl,
            "password_reset": reset_ttl,
        }
        self._email_cooldown = email_cooldown
        self._email_daily_limit = email_daily_limit

    # ── Password accounts ─────────────────────────────────────────────
    async def register(
        self, session: IDbSession, email: str, password: str
    ) -> OutboundAccountEmail | None:
        """Create an unverified account, or e-mail the existing owner. Never signs in.

        Every branch pays one bcrypt hash so response time does not reveal whether
        the address is already registered. Returns the e-mail to send (if any).
        """
        normalized = normalize_email(email)
        validate_new_password(password)
        password_hash = await asyncio.to_thread(self._hasher.hash, password)
        repo = self._repo_factory(session)
        existing = await repo.get_credentials_by_email(normalized)
        if existing is None:
            try:
                account = await repo.create_password_account(normalized, password_hash)
            except EmailAlreadyRegisteredError:
                existing = await repo.get_credentials_by_email(normalized)
                if existing is None:  # pragma: no cover - deleted concurrently
                    return None
            else:
                return await self._issue_email_token(repo, account, "verify_email")
        account = existing.account
        if not account.is_active:
            return None
        # The registrant's password is discarded: only whoever controls the
        # mailbox may set a password on an existing address.
        kind = "existing_account" if account.email_verified else "claim_account"
        return await self._issue_email_token(repo, account, "password_reset", kind=kind)

    async def login(self, session: IDbSession, email: str, password: str) -> IssuedAccountSession:
        try:
            normalized = normalize_email(email)
        except AccountPolicyError:
            await self._burn_hash_time(password)
            raise InvalidCredentialsError from None
        repo = self._repo_factory(session)
        credentials = await repo.get_credentials_by_email(normalized)
        if credentials is None or credentials.password_hash is None:
            await self._burn_hash_time(password)
            raise InvalidCredentialsError
        if not await asyncio.to_thread(
            self._hasher.verify, password, credentials.password_hash
        ):
            raise InvalidCredentialsError
        if not credentials.account.is_active:
            raise InvalidCredentialsError
        if not credentials.account.email_verified:
            # Only someone who knows the password learns the address is pending.
            raise EmailNotVerifiedError
        if self._hasher.needs_rehash(credentials.password_hash):
            rehashed = await asyncio.to_thread(self._hasher.hash, password)
            await repo.update_password_hash(credentials.account.id, rehashed)
        return await self._issue(repo, credentials.account, "password")

    # ── E-mail verification and password recovery ─────────────────────
    async def verify_email(self, session: IDbSession, token: str) -> None:
        repo = self._repo_factory(session)
        account_id = await self._consume_token(repo, "verify_email", token)
        await repo.mark_email_verified(account_id)
        await repo.invalidate_account_tokens(account_id, "verify_email", self._clock())

    async def resend_verification(
        self, session: IDbSession, email: str
    ) -> OutboundAccountEmail | None:
        account = await self._account_for_email(session, email)
        if account is None or account.email_verified or not account.has_password:
            return None
        return await self._issue_email_token(
            self._repo_factory(session), account, "verify_email"
        )

    async def request_password_reset(
        self, session: IDbSession, email: str
    ) -> OutboundAccountEmail | None:
        account = await self._account_for_email(session, email)
        if account is None:
            return None
        kind = "password_reset" if account.email_verified else "claim_account"
        return await self._issue_email_token(
            self._repo_factory(session), account, "password_reset", kind=kind
        )

    async def reset_password(self, session: IDbSession, token: str, new_password: str) -> None:
        """Redeem a reset link: new password, e-mail verified, every session revoked."""
        validate_new_password(new_password)  # before consuming the single-use token
        repo = self._repo_factory(session)
        account_id = await self._consume_token(repo, "password_reset", token)
        account = await repo.get_by_id(account_id)
        if account is None or not account.is_active:
            raise AccountTokenInvalidError
        password_hash = await asyncio.to_thread(self._hasher.hash, new_password)
        now = self._clock()
        await repo.update_password_hash(account_id, password_hash)
        await repo.mark_email_verified(account_id)
        await repo.revoke_all_sessions(account_id, now)
        await repo.invalidate_account_tokens(account_id, "password_reset", now)
        await repo.invalidate_account_tokens(account_id, "verify_email", now)

    async def change_password(
        self,
        session: IDbSession,
        account_id: uuid.UUID,
        current_password: str,
        new_password: str,
    ) -> IssuedAccountSession:
        """Authenticated change: verify the current password, revoke every session,
        and return a fresh session for the caller's browser."""
        repo = self._repo_factory(session)
        credentials = await repo.get_credentials_by_id(account_id)
        if (
            credentials is None
            or credentials.password_hash is None
            or not credentials.account.is_active
        ):
            await self._burn_hash_time(current_password)
            raise InvalidCredentialsError
        if not await asyncio.to_thread(
            self._hasher.verify, current_password, credentials.password_hash
        ):
            raise InvalidCredentialsError
        validate_new_password(new_password)
        password_hash = await asyncio.to_thread(self._hasher.hash, new_password)
        now = self._clock()
        await repo.update_password_hash(account_id, password_hash)
        await repo.revoke_all_sessions(account_id, now)
        await repo.invalidate_account_tokens(account_id, "password_reset", now)
        return await self._issue(repo, credentials.account, "password")

    # ── Sessions ──────────────────────────────────────────────────────
    async def refresh(self, session: IDbSession, refresh_token: str) -> IssuedAccountSession:
        repo = self._repo_factory(session)
        record, account = await self._active_session(repo, refresh_token)
        new_token = secrets.token_urlsafe(32)
        rotated = await repo.rotate_session_token(
            record.id,
            hash_refresh_token(refresh_token),
            hash_refresh_token(new_token),
            self._clock(),
        )
        if not rotated:
            raise SessionInvalidError
        access_token, access_ttl = self._tokens.issue_account_access_token(account.id, record.id)
        return IssuedAccountSession(
            account=account,
            session_id=record.id,
            access_token=access_token,
            access_expires_in=access_ttl,
            refresh_token=new_token,
            refresh_expires_in=max(1, int((record.expires_at - self._clock()).total_seconds())),
        )

    async def logout(self, session: IDbSession, refresh_token: str | None) -> None:
        if not refresh_token:
            return
        repo = self._repo_factory(session)
        record = await repo.get_session_by_token_hash(hash_refresh_token(refresh_token))
        if record is not None and record.revoked_at is None:
            await repo.revoke_session(record.id, self._clock())

    async def account_for_refresh_token(
        self, session: IDbSession, refresh_token: str | None
    ) -> Account | None:
        """Resolve the account behind a still-valid refresh session, without rotating it."""
        if not refresh_token:
            return None
        try:
            _, account = await self._active_session(self._repo_factory(session), refresh_token)
        except SessionInvalidError:
            return None
        return account

    async def get_account(self, session: IDbSession, account_id: uuid.UUID) -> Account | None:
        account = await self._repo_factory(session).get_by_id(account_id)
        return account if account is not None and account.is_active else None

    # ── External identity (Google) ────────────────────────────────────
    async def sign_in_with_external_identity(
        self,
        session: IDbSession,
        identity: VerifiedExternalIdentity,
        *,
        link_to_account_id: uuid.UUID | None = None,
    ) -> IssuedAccountSession:
        repo = self._repo_factory(session)
        existing = await repo.get_by_external_identity(identity.provider, identity.subject)

        if link_to_account_id is not None:
            target = await repo.get_by_id(link_to_account_id)
            if target is None or not target.is_active:
                raise SessionInvalidError
            if existing is not None:
                if existing.id != target.id:
                    raise ExternalIdentityRejectedError("identity is linked to another account")
                return await self._issue(repo, existing, identity.provider)
            if identity.provider in target.linked_providers:
                raise ExternalIdentityRejectedError("account already has this provider linked")
            try:
                account = await repo.link_external_identity(target.id, identity)
            except ExternalIdentityAlreadyLinkedError as error:
                raise ExternalIdentityRejectedError("identity is already linked") from error
            return await self._issue(repo, account, identity.provider)

        if existing is not None:
            if not existing.is_active:
                raise ExternalIdentityRejectedError("account is disabled")
            return await self._issue(repo, existing, identity.provider)

        if not identity.email or not identity.email_verified:
            raise ExternalIdentityRejectedError("provider e-mail is not verified")
        try:
            normalized = normalize_email(identity.email)
        except AccountPolicyError as error:
            raise ExternalIdentityRejectedError("provider e-mail is invalid") from error
        holder = await repo.get_credentials_by_email(normalized)
        if holder is not None:
            # Never merge on e-mail equality. A verified holder must sign in and
            # link; an unverified holder (possibly a squatter) is reclaimed by the
            # mailbox owner through "forgot password" first.
            if not holder.account.email_verified:
                raise EmailClaimRequiredError
            raise AccountLinkRequiredError
        try:
            account = await repo.create_external_account(replace(identity, email=normalized))
        except (EmailAlreadyRegisteredError, ExternalIdentityAlreadyLinkedError) as error:
            raise AccountLinkRequiredError from error
        return await self._issue(repo, account, identity.provider)

    # ── Internals ─────────────────────────────────────────────────────
    async def _active_session(
        self, repo: IAccountRepository, refresh_token: str
    ) -> tuple[AuthSessionRecord, Account]:
        if not refresh_token or len(refresh_token) > 256:
            raise SessionInvalidError
        record = await repo.get_session_by_token_hash(hash_refresh_token(refresh_token))
        now = self._clock()
        if record is None or record.revoked_at is not None or record.expires_at <= now:
            raise SessionInvalidError
        account = await repo.get_by_id(record.account_id)
        if account is None or not account.is_active:
            raise SessionInvalidError
        return record, account

    async def _issue(
        self, repo: IAccountRepository, account: Account, method: AuthMethod
    ) -> IssuedAccountSession:
        refresh_token = secrets.token_urlsafe(32)
        expires_at = self._clock() + self._refresh_ttl
        record = await repo.create_session(
            account.id, hash_refresh_token(refresh_token), expires_at, method
        )
        access_token, access_ttl = self._tokens.issue_account_access_token(account.id, record.id)
        return IssuedAccountSession(
            account=account,
            session_id=record.id,
            access_token=access_token,
            access_expires_in=access_ttl,
            refresh_token=refresh_token,
            refresh_expires_in=int(self._refresh_ttl.total_seconds()),
        )

    async def _account_for_email(self, session: IDbSession, email: str) -> Account | None:
        try:
            normalized = normalize_email(email)
        except AccountPolicyError:
            return None
        credentials = await self._repo_factory(session).get_credentials_by_email(normalized)
        if credentials is None or not credentials.account.is_active:
            return None
        return credentials.account

    async def _issue_email_token(
        self,
        repo: IAccountRepository,
        account: Account,
        purpose: AccountTokenPurpose,
        *,
        kind: str | None = None,
    ) -> OutboundAccountEmail | None:
        """Create a single-use token unless the per-account cooldown/daily cap applies."""
        if not account.email:
            return None
        now = self._clock()
        issued_today, latest = await repo.account_token_activity(
            account.id, purpose, now - timedelta(days=1)
        )
        if issued_today >= self._email_daily_limit:
            return None
        if latest is not None and now - latest < self._email_cooldown:
            return None
        token = secrets.token_urlsafe(32)
        await repo.create_account_token(
            account.id, purpose, hash_account_token(token), now + self._token_ttl[purpose], now
        )
        return OutboundAccountEmail(
            kind=kind or purpose,  # type: ignore[arg-type]
            to=account.email,
            token=token,
        )

    async def _consume_token(
        self, repo: IAccountRepository, purpose: AccountTokenPurpose, token: str
    ) -> uuid.UUID:
        if not isinstance(token, str) or not token or len(token) > _MAX_TOKEN_CHARS:
            raise AccountTokenInvalidError
        account_id = await repo.consume_account_token(
            purpose, hash_account_token(token), self._clock()
        )
        if account_id is None:
            raise AccountTokenInvalidError
        return account_id

    async def _burn_hash_time(self, password: str) -> None:
        """Equalize timing for unknown accounts so login does not reveal registration."""
        if self._dummy_hash is None:
            self._dummy_hash = await asyncio.to_thread(
                self._hasher.hash, secrets.token_urlsafe(16)
            )
        candidate = password if isinstance(password, str) else ""
        await asyncio.to_thread(self._hasher.verify, candidate, self._dummy_hash)
