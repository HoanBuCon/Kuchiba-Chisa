"""Web authentication endpoints: anonymous sessions, accounts and Google sign-in.

Identity is always server-derived: anonymous subjects are minted here, account
subjects are account IDs from the database, and Google identities come only from
a server-side verified ID token. No route accepts a user identifier from the body.

Browser-cookie endpoints (refresh, logout, Google start) require the custom
``X-Chisa-Client`` header; together with ``SameSite=Lax`` cookies this blocks
cross-site request forgery because a foreign page cannot send custom headers to
this origin without a CORS preflight that the API never approves. Every
account-mutating endpoint (register, verification, reset, password change)
requires it too.

E-mail-triggering endpoints (register, resend verification, forgot password)
always answer ``202 {"status": "accepted"}`` and deliver mail in a background
task after the response, so neither the body nor the timing reveals whether an
address has an account.
"""

from __future__ import annotations

import hashlib
import time
import uuid
from typing import Annotated, Any
from urllib.parse import urlencode

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Query,
    Request,
    Response,
    status,
)
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.dependencies import (
    get_account_auth_service,
    get_account_email_dispatcher,
    get_google_identity_provider,
)
from app.application.security.account_email import AccountEmailDispatcher
from app.application.security.accounts import (
    AccountAuthService,
    AccountLinkRequiredError,
    AccountTokenInvalidError,
    EmailClaimRequiredError,
    EmailNotVerifiedError,
    ExternalIdentityRejectedError,
    InvalidCredentialsError,
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
    OutboundAccountEmail,
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
    AcceptedResponse,
    AccountSessionResponse,
    AccountSummary,
    AccountTokenRequest,
    AnonymousSessionResponse,
    AuthCapabilitiesResponse,
    ChangePasswordRequest,
    CurrentIdentityResponse,
    EmailPasswordRequest,
    EmailRequest,
    GoogleStartRequest,
    GoogleStartResponse,
    ResetPasswordRequest,
    StatusResponse,
)

log = get_logger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE = "chisa_refresh"
REFRESH_COOKIE_PATH = "/api/v1/auth"
OAUTH_COOKIE = "chisa_oauth"
OAUTH_COOKIE_PATH = "/api/v1/auth/google"
CLIENT_HEADER = "x-chisa-client"
_INVALID_CREDENTIALS = "Email hoặc mật khẩu không đúng."
_EMAIL_NOT_VERIFIED = (
    "Email chưa được xác minh. Hãy mở liên kết trong email, hoặc gửi lại email xác minh."
)
_INVALID_LINK = "Liên kết không hợp lệ hoặc đã hết hạn."
_EMAIL_UNAVAILABLE = "Đăng ký và khôi phục bằng email tạm thời chưa được bật."

AccountService = Annotated[AccountAuthService, Depends(get_account_auth_service)]
DbSession = Annotated[AsyncSession, Depends(get_db_session)]
EmailDispatcher = Annotated[AccountEmailDispatcher, Depends(get_account_email_dispatcher)]


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


async def _throttle_login_email(email: str, action: str = "login") -> None:
    """Per-address throttle against distributed abuse (the IP limit is separate).

    ``login`` keeps its historical key; e-mail-triggering actions use their own
    buckets so they cannot lock a user out of signing in.
    """
    try:
        normalized = normalize_email(email)
    except AccountPolicyError:
        return
    bucket = "auth-email" if action == "login" else f"auth-email-{action}"
    await _throttle_identity(bucket, normalized)


async def _throttle_identity(bucket: str, identity: str) -> None:
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    try:
        allowed, _, retry_after = await redis_service.consume_token_bucket(
            key=f"chisa:ratelimit:{bucket}:v1:{digest}",
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


def _require_email_delivery(dispatcher: AccountEmailDispatcher) -> None:
    if not dispatcher.enabled:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail=_EMAIL_UNAVAILABLE)


def _accepted(
    background: BackgroundTasks,
    dispatcher: AccountEmailDispatcher,
    outbound: OutboundAccountEmail | None,
) -> JSONResponse:
    """Uniform 202; mail (if any) is sent after the response has been written."""
    if outbound is not None:
        background.add_task(dispatcher.deliver, outbound)
    response = JSONResponse(
        status_code=status.HTTP_202_ACCEPTED, content=AcceptedResponse().model_dump()
    )
    response.headers["Cache-Control"] = "no-store"
    return response


def _account_principal(request: Request) -> PrincipalContext:
    principal = _bearer_principal(request)
    if principal is None or principal.authentication != "account":
        raise HTTPException(status_code=401, detail="Authentication required")
    return principal


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
async def auth_capabilities(dispatcher: EmailDispatcher) -> AuthCapabilitiesResponse:
    return AuthCapabilitiesResponse(
        google=settings.google_oauth_enabled,
        password_registration=dispatcher.enabled,
    )


@router.post("/register", response_model=AcceptedResponse, status_code=202)
async def register(
    body: EmailPasswordRequest,
    request: Request,
    background: BackgroundTasks,
    session: DbSession,
    service: AccountService,
    dispatcher: EmailDispatcher,
) -> JSONResponse:
    """Create an unverified account (or e-mail the existing owner). Never signs in."""
    _require_client_header(request)
    _require_email_delivery(dispatcher)
    await _throttle_login_email(body.email, "register")
    try:
        outbound = await service.register(session, body.email, body.password)
    except AccountPolicyError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    await session.commit()
    log.info("Account registration accepted", email_queued=outbound is not None)
    return _accepted(background, dispatcher, outbound)


@router.post("/verify-email", response_model=StatusResponse)
async def verify_email(
    body: AccountTokenRequest, request: Request, session: DbSession, service: AccountService
) -> JSONResponse:
    _require_client_header(request)
    try:
        await service.verify_email(session, body.token)
    except AccountTokenInvalidError as error:
        raise HTTPException(status_code=400, detail=_INVALID_LINK) from error
    await session.commit()
    log.info("Account e-mail verified")
    response = JSONResponse(content={"status": "verified"})
    response.headers["Cache-Control"] = "no-store"
    return response


@router.post("/verify-email/resend", response_model=AcceptedResponse, status_code=202)
async def resend_verification(
    body: EmailRequest,
    request: Request,
    background: BackgroundTasks,
    session: DbSession,
    service: AccountService,
    dispatcher: EmailDispatcher,
) -> JSONResponse:
    _require_client_header(request)
    _require_email_delivery(dispatcher)
    await _throttle_login_email(body.email, "resend")
    outbound = await service.resend_verification(session, body.email)
    await session.commit()
    return _accepted(background, dispatcher, outbound)


@router.post("/password/forgot", response_model=AcceptedResponse, status_code=202)
async def forgot_password(
    body: EmailRequest,
    request: Request,
    background: BackgroundTasks,
    session: DbSession,
    service: AccountService,
    dispatcher: EmailDispatcher,
) -> JSONResponse:
    _require_client_header(request)
    _require_email_delivery(dispatcher)
    await _throttle_login_email(body.email, "forgot")
    outbound = await service.request_password_reset(session, body.email)
    await session.commit()
    log.info("Password reset requested", email_queued=outbound is not None)
    return _accepted(background, dispatcher, outbound)


@router.post("/password/reset", response_model=StatusResponse)
async def reset_password(
    body: ResetPasswordRequest, request: Request, session: DbSession, service: AccountService
) -> JSONResponse:
    """Redeem a single-use reset link. All refresh sessions are revoked; sign in again."""
    _require_client_header(request)
    try:
        await service.reset_password(session, body.token, body.new_password)
    except AccountPolicyError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except AccountTokenInvalidError as error:
        raise HTTPException(status_code=400, detail=_INVALID_LINK) from error
    await session.commit()
    log.info("Password reset completed")
    response = JSONResponse(content={"status": "password_reset"})
    response.headers["Cache-Control"] = "no-store"
    _clear_refresh_cookie(response)
    return response


@router.post("/password/change", response_model=AccountSessionResponse)
async def change_password(
    body: ChangePasswordRequest, request: Request, session: DbSession, service: AccountService
) -> JSONResponse:
    """Authenticated change: every other session is revoked; this browser gets a new one."""
    _require_client_header(request)
    principal = _account_principal(request)
    await _throttle_identity("auth-password-change", principal.subject_id)
    try:
        issued = await service.change_password(
            session, uuid.UUID(principal.subject_id), body.current_password, body.new_password
        )
    except InvalidCredentialsError as error:
        raise HTTPException(status_code=401, detail="Mật khẩu hiện tại không đúng.") from error
    except AccountPolicyError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    await session.commit()
    log.info("Password changed")
    return _account_session_response(issued, status.HTTP_200_OK)


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
    except EmailNotVerifiedError as error:
        log.info("Account login rejected", reason_code="email_unverified")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=_EMAIL_NOT_VERIFIED
        ) from error
    await session.commit()
    log.info("Account login succeeded", auth_method="password")
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
    log.info("Account logout")
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
    except EmailClaimRequiredError:
        return _app_redirect(auth_error="claim_email")
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
