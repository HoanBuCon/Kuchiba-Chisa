"""Web authentication endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status

from app.application.security.anonymous_session import AnonymousWebSessionService
from app.config.settings import settings
from app.domain.value_objects.principal import PrincipalContext
from app.infrastructure.security.jwt_authenticator import AuthenticationError, jwt_authenticator
from app.interface.api.schemas.auth import AnonymousSessionResponse

router = APIRouter(prefix="/auth", tags=["auth"])


def _verified_web_principal_for_rotation(request: Request) -> PrincipalContext | None:
    authorization = request.headers.get("Authorization")
    if authorization is None:
        return None
    try:
        principal = jwt_authenticator.authenticate_bearer(authorization)
    except AuthenticationError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        ) from error
    if principal.source != "web" or principal.kind != "user":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    return principal


@router.post("/anonymous-session", response_model=AnonymousSessionResponse)
async def issue_anonymous_session(request: Request) -> AnonymousSessionResponse:
    """Mint a new anonymous session or rotate a verified web session.

    The endpoint intentionally accepts no browser-provided user identifier.
    """
    principal = _verified_web_principal_for_rotation(request)
    service = AnonymousWebSessionService(jwt_authenticator, settings.JWT_EXPIRE_MINUTES)
    session = service.issue(principal)
    return AnonymousSessionResponse(
        access_token=session.access_token,
        expires_in=session.expires_in_seconds,
        subject_id=session.subject_id,
    )
