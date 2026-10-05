"""Provider-neutral contracts for end-user accounts and authenticated sessions.

Nothing here knows about OAuth, Google, JWT or password-hashing algorithms. The
domain only sees a verified external identity (provider + stable subject) and an
opaque account identifier that becomes the Core principal subject.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

ExternalProvider = Literal["google"]
AuthMethod = Literal["password", "google"]
# Single-use, e-mailed secrets. Only their SHA-256 is stored.
AccountTokenPurpose = Literal["verify_email", "password_reset"]

_EMAIL_PATTERN = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$")
EMAIL_MAX_LENGTH = 254
PASSWORD_MIN_CHARS = 10
# bcrypt only consumes the first 72 bytes; longer secrets are rejected instead of
# being silently truncated.
PASSWORD_MAX_BYTES = 72


class AccountPolicyError(ValueError):
    """Input violates the account policy (email/password shape)."""


def normalize_email(raw: str) -> str:
    """Canonical comparison form for login/uniqueness; rejects malformed input."""
    email = (raw or "").strip().lower()
    if len(email) > EMAIL_MAX_LENGTH or not _EMAIL_PATTERN.fullmatch(email):
        raise AccountPolicyError("invalid email address")
    return email


def validate_new_password(password: str) -> None:
    if not isinstance(password, str) or len(password) < PASSWORD_MIN_CHARS:
        raise AccountPolicyError(f"password must contain at least {PASSWORD_MIN_CHARS} characters")
    if len(password.encode("utf-8")) > PASSWORD_MAX_BYTES:
        raise AccountPolicyError(f"password must not exceed {PASSWORD_MAX_BYTES} bytes")
    if not password.strip():
        raise AccountPolicyError("password must not be blank")


@dataclass(frozen=True, slots=True)
class Account:
    """A registered end user. ``id`` is the Core user identity (principal subject)."""

    id: uuid.UUID
    email: str | None
    email_verified: bool
    has_password: bool
    linked_providers: tuple[ExternalProvider, ...] = ()
    is_active: bool = True


@dataclass(frozen=True, slots=True)
class AccountCredentials:
    """Repository projection used only inside password verification."""

    account: Account
    password_hash: str | None


@dataclass(frozen=True, slots=True)
class VerifiedExternalIdentity:
    """Identity asserted by an external provider *after* server-side verification.

    ``subject`` is the provider's stable user identifier (OIDC ``sub``); emails are
    informational and are never used as the identity key.
    """

    provider: ExternalProvider
    subject: str
    email: str | None
    email_verified: bool


@dataclass(frozen=True, slots=True)
class AuthSessionRecord:
    """Server-side refresh session; only a hash of the refresh secret is stored."""

    id: uuid.UUID
    account_id: uuid.UUID
    expires_at: datetime
    revoked_at: datetime | None
    auth_method: AuthMethod


@dataclass(frozen=True, slots=True)
class IssuedAccountSession:
    """Credentials returned to the interface layer after a successful sign-in."""

    account: Account
    session_id: uuid.UUID
    access_token: str
    access_expires_in: int
    refresh_token: str
    refresh_expires_in: int


@dataclass(frozen=True, slots=True)
class OutboundAccountEmail:
    """An account e-mail to deliver *after* the transaction commits.

    ``kind`` selects the template: ``verify_email`` (new registration),
    ``password_reset`` (forgot password), ``existing_account`` (someone tried to
    register an address that already has an account) or ``claim_account`` (the
    address is held by an unverified account; resetting proves ownership).
    ``token`` is the raw secret and must never be logged.
    """

    kind: Literal["verify_email", "password_reset", "existing_account", "claim_account"]
    to: str
    token: str
