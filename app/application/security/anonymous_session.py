"""Application service for anonymous web sessions (FR-CH-006, SEC-01)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import uuid4

from app.domain.value_objects.principal import PrincipalContext


@dataclass(frozen=True, slots=True)
class AnonymousWebSession:
    """The opaque browser credential and its server-derived subject."""

    access_token: str
    subject_id: str
    expires_in_seconds: int


class AnonymousWebTokenIssuer(Protocol):
    """Port for signing a server-derived anonymous web session."""

    def issue_anonymous_web_session(self, subject_id: str) -> str: ...


class AnonymousWebSessionService:
    """Mints or rotates a browser session without accepting browser identity."""

    def __init__(self, token_issuer: AnonymousWebTokenIssuer, expiry_minutes: int) -> None:
        self._token_issuer = token_issuer
        self._expiry_minutes = expiry_minutes

    def issue(self, existing_principal: PrincipalContext | None = None) -> AnonymousWebSession:
        if existing_principal is None:
            subject_id = f"web:{uuid4()}"
        else:
            if existing_principal.source != "web" or existing_principal.kind != "user":
                raise ValueError("only a verified web principal may rotate this session")
            subject_id = existing_principal.subject_id

        token = self._token_issuer.issue_anonymous_web_session(subject_id)
        return AnonymousWebSession(
            access_token=token,
            subject_id=subject_id,
            expires_in_seconds=self._expiry_minutes * 60,
        )
