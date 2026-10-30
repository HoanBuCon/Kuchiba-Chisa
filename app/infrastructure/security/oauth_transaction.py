"""Tamper-proof, short-lived OAuth transaction cookie codec (HS256 with SECRET_KEY)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import jwt

from app.application.security.oauth_flow import OAuthTransaction
from app.config.settings import settings

OAUTH_TRANSACTION_TTL = timedelta(minutes=10)
_AUDIENCE = "chisa-oauth-transaction"
_ALGORITHM = "HS256"


class OAuthTransactionError(Exception):
    """Cookie absent, expired, forged or malformed."""


def encode_oauth_transaction(transaction: OAuthTransaction) -> str:
    now = datetime.now(UTC)
    claims = {
        "aud": _AUDIENCE,
        "iss": settings.JWT_ISSUER,
        "iat": now,
        "exp": now + OAUTH_TRANSACTION_TTL,
        "state": transaction.state,
        "nonce": transaction.nonce,
        "cv": transaction.code_verifier,
        "link": str(transaction.link_account_id) if transaction.link_account_id else None,
    }
    return jwt.encode(claims, settings.SECRET_KEY, algorithm=_ALGORITHM)


def decode_oauth_transaction(value: str | None) -> OAuthTransaction:
    if not value:
        raise OAuthTransactionError("missing OAuth transaction")
    try:
        claims = jwt.decode(
            value,
            settings.SECRET_KEY,
            algorithms=[_ALGORITHM],
            audience=_AUDIENCE,
            issuer=settings.JWT_ISSUER,
            options={"require": ["exp", "iat"]},
        )
        link = claims.get("link")
        return OAuthTransaction(
            state=str(claims["state"]),
            nonce=str(claims["nonce"]),
            code_verifier=str(claims["cv"]),
            link_account_id=uuid.UUID(link) if link else None,
        )
    except (jwt.PyJWTError, KeyError, ValueError, TypeError) as error:
        raise OAuthTransactionError("invalid OAuth transaction") from error
