"""HTTP contract for registered accounts and Google sign-in (in-memory persistence)."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from urllib.parse import parse_qs, urlsplit

import pytest
import pytest_asyncio
from account_fakes import (
    FakeDbSession,
    InMemoryAccountRepository,
    OutboxSender,
    make_dispatcher,
    make_service,
    token_from_email,
)
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.application.dependencies import (
    get_account_auth_service,
    get_account_email_dispatcher,
    get_google_identity_provider,
)
from app.config.settings import settings
from app.domain.interfaces.accounts import IExternalIdentityProvider
from app.domain.models.account import VerifiedExternalIdentity
from app.infrastructure.cache.redis.redis_service import redis_service
from app.infrastructure.database.engine import get_db_session
from app.infrastructure.security.jwt_authenticator import jwt_authenticator
from app.interface.api.routes import auth
from app.interface.middlewares.rate_limiter import RateLimitMiddleware

PASSWORD = "correct horse battery"
WEB = {"X-Chisa-Client": "web"}
APP_URL = "https://chisa.example.test"


class FakeGoogleProvider(IExternalIdentityProvider):
    def __init__(self) -> None:
        self.identity = VerifiedExternalIdentity(
            provider="google", subject="g-sub-1", email="senpai@gmail.com", email_verified=True
        )
        self.last_nonce: str | None = None
        self.last_verifier: str | None = None

    @property
    def provider(self):
        return "google"

    def authorization_url(self, *, state: str, nonce: str, code_challenge: str) -> str:
        return (
            "https://accounts.google.com/o/oauth2/v2/auth?"
            f"state={state}&nonce={nonce}&code_challenge={code_challenge}"
        )

    async def exchange_code(self, *, code: str, code_verifier: str, nonce: str):
        if code != "good-code":
            raise RuntimeError("rejected")
        self.last_nonce = nonce
        self.last_verifier = code_verifier
        return self.identity


@pytest_asyncio.fixture
async def env(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[dict]:
    monkeypatch.setattr(settings, "PUBLIC_APP_URL", APP_URL)
    monkeypatch.setattr(settings, "AUTH_COOKIE_SECURE", True)

    async def unlimited(**_: object) -> tuple[bool, int, float]:
        return True, 10, 0.0

    monkeypatch.setattr(redis_service, "consume_token_bucket", unlimited)

    repo = InMemoryAccountRepository()
    google = FakeGoogleProvider()
    outbox = OutboxSender()
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware)
    app.include_router(auth.router, prefix="/api/v1")

    async def fake_session() -> AsyncIterator[FakeDbSession]:
        yield FakeDbSession()

    app.dependency_overrides[get_db_session] = fake_session
    app.dependency_overrides[get_account_auth_service] = lambda: make_service(repo)
    app.dependency_overrides[get_google_identity_provider] = lambda: google
    dispatcher = make_dispatcher(outbox, APP_URL)
    app.dependency_overrides[get_account_email_dispatcher] = lambda: dispatcher
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://testserver"
    ) as client:
        yield {"client": client, "repo": repo, "google": google, "outbox": outbox}


async def register(client: AsyncClient, email: str = "senpai@example.com"):
    return await client.post(
        "/api/v1/auth/register", json={"email": email, "password": PASSWORD}, headers=WEB
    )


async def signup(env: dict, email: str = "senpai@example.com"):
    """Register → open the e-mailed verification link → sign in. Returns the login reply."""
    client = env["client"]
    assert (await register(client, email)).status_code == 202
    token = token_from_email(env["outbox"].sent[-1])
    verified = await client.post("/api/v1/auth/verify-email", json={"token": token}, headers=WEB)
    assert verified.status_code == 200, verified.text
    login = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": PASSWORD}, headers=WEB
    )
    assert login.status_code == 200, login.text
    return login


async def signup_existing(env: dict, email: str = "senpai@example.com"):
    client = env["client"]
    token = token_from_email(env["outbox"].sent[-1])
    await client.post("/api/v1/auth/verify-email", json={"token": token}, headers=WEB)
    return await client.post(
        "/api/v1/auth/login", json={"email": email, "password": PASSWORD}, headers=WEB
    )


def _cookie_header(response, name: str) -> str:
    return next(v for v in response.headers.get_list("set-cookie") if v.startswith(f"{name}="))


@pytest.mark.asyncio
async def test_register_returns_account_session_and_hardened_refresh_cookie(env) -> None:
    registered = await register(env["client"])
    assert registered.status_code == 202
    assert registered.json() == {"status": "accepted"}
    assert "set-cookie" not in registered.headers  # no session before verification

    response = await signup_existing(env)
    body = response.json()
    principal = jwt_authenticator.authenticate_bearer(f"Bearer {body['access_token']}")
    assert principal.subject_id == body["subject_id"]
    assert principal.authentication == "account"
    assert body["account"] == {
        "email": "senpai@example.com",
        "email_verified": True,
        "has_password": True,
        "providers": [],
    }
    assert "refresh_token" not in body and PASSWORD not in response.text
    cookie = _cookie_header(response, "chisa_refresh").lower()
    for attribute in ("httponly", "secure", "samesite=lax", "path=/api/v1/auth"):
        assert attribute in cookie
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.asyncio
async def test_register_rejects_client_supplied_identity_fields(env) -> None:
    response = await env["client"].post(
        "/api/v1/auth/register",
        json={"email": "a@example.com", "password": PASSWORD, "user_id": "victim"},
        headers=WEB,
    )
    assert response.status_code == 422
    assert env["repo"].accounts == {}


@pytest.mark.asyncio
async def test_cookie_endpoints_require_the_client_header(env) -> None:
    client = env["client"]
    credentials = {"email": "a@example.com", "password": PASSWORD}
    for path, body in (
        ("register", credentials),
        ("login", credentials),
        ("refresh", None),
        ("logout", None),
        ("google/start", {}),
        ("verify-email", {"token": "x" * 43}),
        ("verify-email/resend", {"email": "a@example.com"}),
        ("password/forgot", {"email": "a@example.com"}),
        ("password/reset", {"token": "x" * 43, "new_password": PASSWORD}),
        ("password/change", {"current_password": PASSWORD, "new_password": PASSWORD}),
    ):
        response = await client.post(f"/api/v1/auth/{path}", json=body)
        assert response.status_code == 403, path
    assert env["repo"].accounts == {}
    assert env["outbox"].sent == []


@pytest.mark.asyncio
async def test_login_error_does_not_reveal_account_existence(env, caplog) -> None:
    client = env["client"]
    await signup(env)
    caplog.set_level(logging.DEBUG)

    wrong = await client.post(
        "/api/v1/auth/login",
        json={"email": "senpai@example.com", "password": "wrong password!"},
        headers=WEB,
    )
    unknown = await client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@example.com", "password": "wrong password!"},
        headers=WEB,
    )
    ok = await client.post(
        "/api/v1/auth/login",
        json={"email": "SENPAI@example.com", "password": PASSWORD},
        headers=WEB,
    )

    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()
    assert ok.status_code == 200
    assert PASSWORD not in caplog.text
    assert "wrong password!" not in caplog.text
    assert ok.json()["access_token"] not in caplog.text


@pytest.mark.asyncio
async def test_registration_does_not_reveal_existing_addresses(env) -> None:
    client = env["client"]
    await signup(env)
    fresh = await register(client, "brand-new@example.com")
    existing = await register(client, "SENPAI@example.com")

    assert fresh.status_code == existing.status_code == 202
    assert fresh.json() == existing.json() == {"status": "accepted"}
    assert fresh.headers.get("set-cookie") is None and existing.headers.get("set-cookie") is None
    assert len(env["repo"].accounts) == 2
    # Each address hears only about itself: verification vs. "already registered".
    sent = {m.to: m.subject for m in env["outbox"].sent[-2:]}
    assert "Xác minh" in sent["brand-new@example.com"]
    assert "đã có tài khoản" in sent["senpai@example.com"]


@pytest.mark.asyncio
async def test_refresh_rotates_cookie_and_logout_revokes(env) -> None:
    client = env["client"]
    await signup(env)

    refreshed = await client.post("/api/v1/auth/refresh", headers=WEB)
    assert refreshed.status_code == 200
    assert refreshed.json()["account"]["email"] == "senpai@example.com"

    logout = await client.post("/api/v1/auth/logout", headers=WEB)
    assert logout.status_code == 204
    assert "max-age=0" in _cookie_header(logout, "chisa_refresh").lower()
    assert all(s["revoked_at"] is not None for s in env["repo"].sessions.values())

    after = await client.post("/api/v1/auth/refresh", headers=WEB)
    assert after.status_code == 401


@pytest.mark.asyncio
async def test_account_token_cannot_be_downgraded_to_anonymous_session(env) -> None:
    client = env["client"]
    token = (await signup(env)).json()["access_token"]

    response = await client.post(
        "/api/v1/auth/anonymous-session", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_me_reports_server_derived_identity(env) -> None:
    client = env["client"]
    body = (await signup(env)).json()

    me = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"}
    )
    assert me.status_code == 200
    assert me.json()["authenticated"] is True
    assert me.json()["subject_id"] == body["subject_id"]

    anonymous = (await client.post("/api/v1/auth/anonymous-session")).json()
    me_anon = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {anonymous['access_token']}"}
    )
    assert me_anon.json() == {
        "authenticated": False,
        "authentication": "anonymous",
        "subject_id": anonymous["subject_id"],
        "account": None,
    }


async def _google_start(client: AsyncClient, intent: str = "login", token: str | None = None):
    headers = dict(WEB)
    if token:
        headers["Authorization"] = f"Bearer {token}"
    response = await client.post(
        "/api/v1/auth/google/start", json={"intent": intent}, headers=headers
    )
    assert response.status_code == 200, response.text
    query = parse_qs(urlsplit(response.json()["authorization_url"]).query)
    oauth_cookie = _cookie_header(response, "chisa_oauth").lower()
    assert "httponly" in oauth_cookie and "path=/api/v1/auth/google" in oauth_cookie
    return query["state"][0], query["nonce"][0]


def _redirect_params(response) -> dict[str, list[str]]:
    assert response.status_code == 303
    location = response.headers["location"]
    assert location.startswith(APP_URL + "/")
    return parse_qs(urlsplit(location).query)


@pytest.mark.asyncio
async def test_google_login_creates_account_and_sets_session_cookie(env) -> None:
    client = env["client"]
    state, nonce = await _google_start(client)

    callback = await client.get(
        "/api/v1/auth/google/callback", params={"code": "good-code", "state": state}
    )
    assert _redirect_params(callback) == {"auth": ["google"]}
    assert "chisa_refresh=" in callback.headers.get("set-cookie", "")
    assert env["google"].last_nonce == nonce
    assert env["google"].last_verifier and len(env["google"].last_verifier) >= 43
    assert "good-code" not in callback.headers["location"]

    session = await client.post("/api/v1/auth/refresh", headers=WEB)
    assert session.status_code == 200
    assert session.json()["account"]["providers"] == ["google"]


@pytest.mark.asyncio
async def test_google_callback_rejects_missing_or_mismatched_state(env) -> None:
    client = env["client"]
    no_tx = await client.get(
        "/api/v1/auth/google/callback", params={"code": "good-code", "state": "x"}
    )
    assert _redirect_params(no_tx) == {"auth_error": ["expired"]}

    await _google_start(client)
    forged = await client.get(
        "/api/v1/auth/google/callback", params={"code": "good-code", "state": "attacker-state"}
    )
    assert _redirect_params(forged) == {"auth_error": ["state"]}
    assert env["repo"].accounts == {}


@pytest.mark.asyncio
async def test_google_email_collision_requires_explicit_link(env) -> None:
    client = env["client"]
    await signup(env, "senpai@gmail.com")
    await client.post("/api/v1/auth/logout", headers=WEB)

    state, _ = await _google_start(client)
    callback = await client.get(
        "/api/v1/auth/google/callback", params={"code": "good-code", "state": state}
    )
    assert _redirect_params(callback) == {"auth_error": ["link_required"]}
    assert env["repo"].identities == {}


@pytest.mark.asyncio
async def test_signed_in_account_links_google_then_can_sign_in_with_it(env) -> None:
    client = env["client"]
    token = (await signup(env, "senpai@gmail.com")).json()["access_token"]
    owner_id = next(iter(env["repo"].accounts))

    state, _ = await _google_start(client, "link", token)
    callback = await client.get(
        "/api/v1/auth/google/callback", params={"code": "good-code", "state": state}
    )
    assert _redirect_params(callback) == {"auth": ["google"]}
    assert env["repo"].identities == {("google", "g-sub-1"): owner_id}


@pytest.mark.asyncio
async def test_link_requires_account_token_and_same_browser_session(env) -> None:
    client = env["client"]
    anonymous = (await client.post("/api/v1/auth/anonymous-session")).json()["access_token"]
    refused = await client.post(
        "/api/v1/auth/google/start",
        json={"intent": "link"},
        headers={**WEB, "Authorization": f"Bearer {anonymous}"},
    )
    assert refused.status_code == 401

    token = (await signup(env, "senpai@gmail.com")).json()["access_token"]
    state, _ = await _google_start(client, "link", token)
    client.cookies.delete("chisa_refresh", path="/api/v1/auth")
    callback = await client.get(
        "/api/v1/auth/google/callback", params={"code": "good-code", "state": state}
    )
    assert _redirect_params(callback) == {"auth_error": ["session"]}
    assert env["repo"].identities == {}


@pytest.mark.asyncio
async def test_google_unavailable_when_not_configured(env) -> None:
    client = env["client"]
    client._transport.app.dependency_overrides[get_google_identity_provider] = lambda: None
    response = await client.post("/api/v1/auth/google/start", json={}, headers=WEB)
    assert response.status_code == 503


@pytest.mark.asyncio
async def test_login_and_register_are_rate_limited_per_client(env, monkeypatch) -> None:
    async def redis_down(**_: object) -> tuple[bool, int, float]:
        raise ConnectionError("redis unavailable")

    monkeypatch.setattr(redis_service, "consume_token_bucket", redis_down)
    monkeypatch.setattr(settings, "AUTH_RATE_LIMIT_PER_MINUTE", 3)
    client = env["client"]

    statuses = [
        (
            await client.post(
                "/api/v1/auth/login",
                json={"email": "nobody@example.com", "password": "wrong password!"},
                headers=WEB,
            )
        ).status_code
        for _ in range(4)
    ]
    assert statuses == [401, 401, 401, 429]


@pytest.mark.asyncio
async def test_login_is_throttled_per_email(env, monkeypatch) -> None:
    calls: list[str] = []

    async def bucket(**kwargs: object) -> tuple[bool, int, float]:
        calls.append(str(kwargs["key"]))
        return (not str(kwargs["key"]).startswith("chisa:ratelimit:auth-email"), 0, 30.0)

    monkeypatch.setattr(redis_service, "consume_token_bucket", bucket)
    response = await env["client"].post(
        "/api/v1/auth/login",
        json={"email": "senpai@example.com", "password": PASSWORD},
        headers=WEB,
    )
    assert response.status_code == 429
    assert all("senpai" not in key for key in calls)
