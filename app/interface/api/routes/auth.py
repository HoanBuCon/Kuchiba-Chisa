"""Web authentication endpoints: anonymous sessions, accounts and Google sign-in.

Identity is always server-derived: anonymous subjects are minted here, account
subjects are account IDs from the database, and Google identities come only from
a server-side verified ID token. No route accepts a user identifier from the body.

Browser-cookie endpoints (refresh, logout, Google start) require the custom
``X-Chisa-Client`` header; together with ``SameSite=Lax`` cookies this blocks
cross-site request forgery because a foreign page cannot send custom headers to
this origin without a CORS preflight that the API never approves.
"""

from __future__ import annotations

import hashlib
import time
import uuid
from typing import Annotated, Any
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.dependencies import (
    get_account_auth_service,
    get_google_identity_provider,
)
from app.application.security.accounts import (
    AccountAuthService,
    AccountLinkRequiredError,
    ExternalIdentityRejectedError,
    InvalidCredentialsError,
    RegistrationRejectedError,
    SessionInvalidError,
)
from app.application.security.anonymous_session import AnonymousWebSessionService
from app.application.security.oauth_flow import new_oauth_transaction, state_matches
from app.config.settings import settings
from app.domain.interfaces.accounts import IExternalIdentityProvider
from app.domain.models.account import (
    Account,
    AccountPolicyError,
    IssuedAccountSession,
    normalize_email,
)
from app.domain.value_objects.principal import PrincipalContext
from app.infrastructure.cache.redis.redis_service import redis_service
from app.infrastructure.database.engine import get_db_session
from app.infrastructure.logging.logger import get_logger
from app.infrastructure.security.jwt_authenticator import AuthenticationError, jwt_authenticator
from app.infrastructure.security.oauth_transaction import (
    OAUTH_TRANSACTION_TTL,
    OAuthTransactionError,
    decode_oauth_transaction,
    encode_oauth_transaction,
)
from app.interface.api.dependencies.security import CurrentPrincipal
from app.interface.api.schemas.auth import (
    AccountSessionResponse,
    AccountSummary,
    AnonymousSessionResponse,
    AuthCapabilitiesResponse,
    CurrentIdentityResponse,
    EmailPasswordRequest,
    GoogleStartRequest,
    GoogleStartResponse,
)

log = get_logger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE = "chisa_refresh"
REFRESH_COOKIE_PATH = "/api/v1/auth"
OAUTH_COOKIE = "chisa_oauth"
OAUTH_COOKIE_PATH = "/api/v1/auth/google"
CLIENT_HEADER = "x-chisa-client"
_INVALID_CREDENTIALS = "Email hoặc mật khẩu không đúng."

AccountService = Annotated[AccountAuthService, Depends(get_account_auth_service)]
DbSession = Annotated[AsyncSession, Depends(get_db_session)]


# ── Helpers ───────────────────────────────────────────────────────────────


def _require_client_header(request: Request) -> None:
    if request.headers.get(CLIENT_HEADER) != "web":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")


def _bearer_principal(request: Request) -> PrincipalContext | None:
    authorization = request.headers.get("Authorization")
    if authorization is None:
        return None
    try:
        return jwt_authenticator.authenticate_bearer(authorization)
    except AuthenticationError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        ) from error


def _summary(account: Account) -> AccountSummary:
    return AccountSummary(
        email=account.email,
        email_verified=account.email_verified,
        has_password=account.has_password,
        providers=list(account.linked_providers),
    )


def _set_refresh_cookie(response: Response, issued: IssuedAccountSession) -> None:
    response.set_cookie(
        REFRESH_COOKIE,
        issued.refresh_token,
        max_age=issued.refresh_expires_in,
        httponly=True,
        secure=settings.AUTH_COOKIE_SECURE,
        samesite="lax",
        path=REFRESH_COOKIE_PATH,
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        REFRESH_COOKIE,
        path=REFRESH_COOKIE_PATH,
        httponly=True,
        secure=settings.AUTH_COOKIE_SECURE,
        samesite="lax",
    )


def _session_payload(issued: IssuedAccountSession) -> dict[str, Any]:
    return AccountSessionResponse(
        access_token=issued.access_token,
        expires_in=issued.access_expires_in,
        subject_id=str(issued.account.id),
        account=_summary(issued.account),
    ).model_dump()


def _account_session_response(issued: IssuedAccountSession, status_code: int) -> JSONResponse:
    response = JSONResponse(status_code=status_code, content=_session_payload(issued))
    response.headers["Cache-Control"] = "no-store"
    _set_refresh_cookie(response, issued)
    return response


async def _throttle_login_email(email: str) -> None:
    """Per-account throttle against distributed credential stuffing (IP limit is separate)."""
    try:
        normalized = normalize_email(email)
    except AccountPolicyError:
        return
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    try:
        allowed, _, retry_after = await redis_service.consume_token_bucket(
            key=f"chisa:ratelimit:auth-email:v1:{digest}",
            capacity=settings.AUTH_LOGIN_PER_EMAIL_PER_MINUTE,
            refill_period_seconds=60,
            now=time.time(),
        )
    except Exception as error:
        log.warning("Login e-mail throttle unavailable", error_type=type(error).__name__)
        return
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded",
            headers={"Retry-After": str(max(1, int(retry_after)))},
        )


# ── Anonymous sessions (compatibility) ────────────────────────────────────


@router.post("/anonymous-session", response_model=AnonymousSessionResponse)
async def issue_anonymous_session(request: Request) -> AnonymousSessionResponse:
    """Mint a new anonymous session or rotate a verified *anonymous* web session.

    Account sessions are never converted into anonymous tokens: that would let a
    logged-out (revoked) account keep minting credentials for its subject.
    """
    principal = _bearer_principal(request)
    if principal is not None and (
        principal.source != "web"
        or principal.kind != "user"
        or principal.authentication != "anonymous"
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    service = AnonymousWebSessionService(jwt_authenticator, settings.JWT_EXPIRE_MINUTES)
    session = service.issue(principal)
    return AnonymousSessionResponse(
        access_token=session.access_token,
        expires_in=session.expires_in_seconds,
        subject_id=session.subject_id,
    )


# ── Registered accounts ───────────────────────────────────────────────────


@router.get("/capabilities", response_model=AuthCapabilitiesResponse)
async def auth_capabilities() -> AuthCapabilitiesResponse:
    return AuthCapabilitiesResponse(google=settings.google_oauth_enabled)


@router.post("/register", response_model=AccountSessionResponse, status_code=201)
async def register(
    body: EmailPasswordRequest,
    request: Request,
    session: DbSession,
    service: AccountService,
) -> JSONResponse:
    _require_client_header(request)
    try:
        issued = await service.register(session, body.email, body.password)
    except AccountPolicyError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except RegistrationRejectedError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Không thể đăng ký với email này.",
        ) from error
    await session.commit()
    log.info("Account registered", auth_method="password")
    return _account_session_response(issued, status.HTTP_201_CREATED)


@router.post("/login", response_model=AccountSessionResponse)
async def login(
    body: EmailPasswordRequest,
    request: Request,
    session: DbSession,
    service: AccountService,
) -> JSONResponse:
    _require_client_header(request)
    await _throttle_login_email(body.email)
    try:
        issued = await service.login(session, body.email, body.password)
    except InvalidCredentialsError as error:
        log.info("Account login rejected")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=_INVALID_CREDENTIALS
        ) from error
    await session.commit()
    return _account_session_response(issued, status.HTTP_200_OK)


@router.post("/refresh", response_model=AccountSessionResponse)
async def refresh(request: Request, session: DbSession, service: AccountService) -> JSONResponse:
    _require_client_header(request)
    try:
        issued = await service.refresh(session, request.cookies.get(REFRESH_COOKIE, ""))
    except SessionInvalidError:
        response = JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"detail": "Session expired"},
        )
        _clear_refresh_cookie(response)
        return response
    await session.commit()
    return _account_session_response(issued, status.HTTP_200_OK)


@router.post("/logout", status_code=204)
async def logout(request: Request, session: DbSession, service: AccountService) -> Response:
    _require_client_header(request)
    await service.logout(session, request.cookies.get(REFRESH_COOKIE))
    await session.commit()
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    _clear_refresh_cookie(response)
    return response


@router.get("/me", response_model=CurrentIdentityResponse)
async def me(
    principal: CurrentPrincipal, session: DbSession, service: AccountService
) -> CurrentIdentityResponse:
    account = None
    if principal.authentication == "account":
        found = await service.get_account(session, uuid.UUID(principal.subject_id))
        if found is None:
            raise HTTPException(status_code=401, detail="Authentication required")
        account = _summary(found)
    return CurrentIdentityResponse(
        authenticated=principal.authentication == "account",
        authentication=principal.authentication,
        subject_id=principal.subject_id,
        account=account,
    )


# ── Google OpenID Connect (Authorization Code + PKCE) ─────────────────────


GoogleProvider = Annotated[IExternalIdentityProvider | None, Depends(get_google_identity_provider)]


@router.post("/google/start", response_model=GoogleStartResponse)
async def google_start(
    body: GoogleStartRequest,
    request: Request,
    provider: GoogleProvider,
) -> JSONResponse:
    """Create a browser-bound OAuth transaction and return Google's authorization URL.

    Linking requires a verified *account* access token; the account to link is
    taken from that token, never from request parameters.
    """
    _require_client_header(request)
    if provider is None:
        raise HTTPException(status_code=503, detail="Google sign-in is not configured")
    link_account_id = None
    if body.intent == "link":
        principal = _bearer_principal(request)
        if principal is None or principal.authentication != "account":
            raise HTTPException(status_code=401, detail="Authentication required")
        link_account_id = uuid.UUID(principal.subject_id)
    transaction = new_oauth_transaction(link_account_id)
    response = JSONResponse(
        content=GoogleStartResponse(
            authorization_url=provider.authorization_url(
                state=transaction.state,
                nonce=transaction.nonce,
                code_challenge=transaction.code_challenge,
            )
        ).model_dump()
    )
    response.headers["Cache-Control"] = "no-store"
    response.set_cookie(
        OAUTH_COOKIE,
        encode_oauth_transaction(transaction),
        max_age=int(OAUTH_TRANSACTION_TTL.total_seconds()),
        httponly=True,
        secure=settings.AUTH_COOKIE_SECURE,
        samesite="lax",
        path=OAUTH_COOKIE_PATH,
    )
    return response


def _app_redirect(**params: str) -> RedirectResponse:
    target = settings.PUBLIC_APP_URL.rstrip("/") + "/"
    response = RedirectResponse(f"{target}?{urlencode(params)}", status_code=303)
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.delete_cookie(
        OAUTH_COOKIE,
        path=OAUTH_COOKIE_PATH,
        httponly=True,
        secure=settings.AUTH_COOKIE_SECURE,
        samesite="lax",
    )
    return response


@router.get("/google/callback", include_in_schema=False)
async def google_callback(
    request: Request,
    session: DbSession,
    service: AccountService,
    provider: GoogleProvider,
    code: Annotated[str | None, Query(max_length=2048)] = None,
    state: Annotated[str | None, Query(max_length=512)] = None,
    error: Annotated[str | None, Query(max_length=128)] = None,
) -> RedirectResponse:
    """Complete Google sign-in. Every failure redirects with a coarse, non-sensitive code."""
    if provider is None:
        return _app_redirect(auth_error="unavailable")
    if error:
        return _app_redirect(auth_error="cancelled")
    try:
        transaction = decode_oauth_transaction(request.cookies.get(OAUTH_COOKIE))
    except OAuthTransactionError:
        return _app_redirect(auth_error="expired")
    if not state_matches(transaction.state, state) or not code:
        log.warning("Google callback rejected", reason_code="state_mismatch")
        return _app_redirect(auth_error="state")

    if transaction.link_account_id is not None:
        # Defense in depth: the browser completing a link must still hold the
        # refresh session of the account that started it.
        current = await service.account_for_refresh_token(
            session, request.cookies.get(REFRESH_COOKIE)
        )
        if current is None or current.id != transaction.link_account_id:
            return _app_redirect(auth_error="session")

    try:
        identity = await provider.exchange_code(
            code=code, code_verifier=transaction.code_verifier, nonce=transaction.nonce
        )
    except Exception as exc:  # provider adapters raise typed, token-free errors
        log.warning("Google identity verification failed", error_type=type(exc).__name__)
        return _app_redirect(auth_error="failed")

    try:
        issued = await service.sign_in_with_external_identity(
            session, identity, link_to_account_id=transaction.link_account_id
        )
    except AccountLinkRequiredError:
        return _app_redirect(auth_error="link_required")
    except (ExternalIdentityRejectedError, SessionInvalidError):
        return _app_redirect(auth_error="rejected")
    await session.commit()
    log.info(
        "Google sign-in completed",
        linked=transaction.link_account_id is not None,
    )
    response = _app_redirect(auth="google")
    _set_refresh_cookie(response, issued)
    return response
