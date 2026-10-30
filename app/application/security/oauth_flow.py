"""Browser-bound OAuth transaction values (state, nonce, PKCE) — provider neutral."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import uuid
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class OAuthTransaction:
    """Secrets that must round-trip through the user's browser, and only it.

    ``link_account_id`` is set only when an already authenticated account asked to
    link an external identity; it is taken from the verified access token, never
    from request parameters.
    """

    state: str
    nonce: str
    code_verifier: str
    link_account_id: uuid.UUID | None = None

    @property
    def code_challenge(self) -> str:
        digest = hashlib.sha256(self.code_verifier.encode("ascii")).digest()
        return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def new_oauth_transaction(link_account_id: uuid.UUID | None = None) -> OAuthTransaction:
    # RFC 7636: verifier of 43-128 unreserved characters; 64 random bytes → 86 chars.
    return OAuthTransaction(
        state=secrets.token_urlsafe(32),
        nonce=secrets.token_urlsafe(32),
        code_verifier=secrets.token_urlsafe(64),
        link_account_id=link_account_id,
    )


def state_matches(expected: str, received: str | None) -> bool:
    return bool(received) and hmac.compare_digest(expected, received or "")
