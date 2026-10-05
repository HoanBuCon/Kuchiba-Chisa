"""HTTP contract for verification, password reset/change and e-mail delivery (A-01/A-02)."""

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
from test_account_routes import FakeGoogleProvider

from app.application.dependencies import (
    get_account_auth_service,
    get_account_email_dispatcher,
    get_google_identity_provider,
)
from app.application.security.account_email import AccountEmailDispatcher
from app.config.settings import settings
from app.domain.models.account import OutboundAccountEmail
from app.infrastructure.cache.redis.redis_service import redis_service
from app.infrastructure.database.engine import get_db_session
from app.interface.api.routes import auth
from app.interface.middlewares.rate_limiter import RateLimitMiddleware

PASSWORD = "correct horse battery"
NEW_PASSWORD = "brand new passphrase"
WEB = {"X-Chisa-Client": "web"}
APP_URL = "https://chisa.example.test"
EMAIL = "senpai@example.com"


@pytest_asyncio.fixture
async def env(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[dict]:
    monkeypatch.setattr(settings, "PUBLIC_APP_URL", APP_URL)
    monkeypatch.setattr(settings, "AUTH_COOKIE_SECURE", True)

    async def unlimited(**_: object) -> tuple[bool, int, float]:
        return True, 10, 0.0

    monkeypatch.setattr(redis_service, "consume_token_bucket", unlimited)
    repo = InMemoryAccountRepository()
    outbox = OutboxSender()
    google = FakeGoogleProvider()
    holder = {"dispatcher": make_dispatcher(outbox, APP_URL)}
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware)
    app.include_router(auth.router, prefix="/api/v1")

    async def fake_session() -> AsyncIterator[FakeDbSession]:
        yield FakeDbSession()

    app.dependency_overrides[get_db_session] = fake_session
    app.dependency_overrides[get_account_auth_service] = lambda: make_service(repo)
    app.dependency_overrides[get_account_email_dispatcher] = lambda: holder["dispatcher"]
    app.dependency_overrides[get_google_identity_provider] = lambda: google
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://testserver"
    ) as client:
        yield {"client": client, "repo": repo, "outbox": outbox, "holder": holder}


async def _post(client: AsyncClient, path: str, body: dict | None = None, headers=None):
    return await client.post(f"/api/v1/auth/{path}", json=body, headers=headers or WEB)


async def _signup(env: dict, email: str = EMAIL):
    client = env["client"]
    await _post(client, "register", {"email": email, "password": PASSWORD})
    token = token_from_email(env["outbox"].sent[-1])
    await _post(client, "verify-email", {"token": token})
    return await _post(client, "login", {"email": email, "password": PASSWORD})


@pytest.mark.asyncio
async def test_login_of_unverified_account_is_refused_without_a_session(env) -> None:
    client = env["client"]
    await _post(client, "register", {"email": EMAIL, "password": PASSWORD})
    response = await _post(client, "login", {"email": EMAIL, "password": PASSWORD})

    assert response.status_code == 403
    assert "xác minh" in response.json()["detail"]
    assert "set-cookie" not in response.headers
    assert env["repo"].sessions == {}


@pytest.mark.asyncio
async def test_verification_link_uses_url_fragment_and_is_single_use(env) -> None:
    client = env["client"]
    await _post(client, "register", {"email": EMAIL, "password": PASSWORD})
    message = env["outbox"].sent[-1]
    assert message.to == EMAIL
    assert f"{APP_URL}/#verify-email=" in message.text  # fragment: never sent to servers
    token = token_from_email(message)

    assert (await _post(client, "verify-email", {"token": token})).status_code == 200
    reused = await _post(client, "verify-email", {"token": token})
    assert reused.status_code == 400
    assert reused.json() == {"detail": "Liên kết không hợp lệ hoặc đã hết hạn."}


@pytest.mark.asyncio
async def test_forgot_password_response_is_identical_for_known_and_unknown_addresses(env) -> None:
    client = env["client"]
    await _signup(env)
    sent_before = len(env["outbox"].sent)

    unknown = await _post(client, "password/forgot", {"email": "nobody@example.com"})
    known = await _post(client, "password/forgot", {"email": "SENPAI@example.com"})
    malformed = await _post(client, "password/forgot", {"email": "not-an-email"})

    assert unknown.status_code == known.status_code == malformed.status_code == 202
    assert unknown.json() == known.json() == malformed.json() == {"status": "accepted"}
    assert unknown.headers["cache-control"] == known.headers["cache-control"] == "no-store"
    new_mail = env["outbox"].sent[sent_before:]
    assert [m.to for m in new_mail] == [EMAIL]
    assert f"{APP_URL}/#reset-password=" in new_mail[0].text


@pytest.mark.asyncio
async def test_reset_revokes_all_sessions_and_token_cannot_be_reused(env, caplog, capsys) -> None:
    caplog.set_level(logging.DEBUG)
    client = env["client"]
    login = await _signup(env)
    access_token = login.json()["access_token"]

    await _post(client, "password/forgot", {"email": EMAIL})
    token = token_from_email(env["outbox"].sent[-1])
    reset = await _post(client, "password/reset", {"token": token, "new_password": NEW_PASSWORD})
    assert reset.status_code == 200
    assert "max-age=0" in reset.headers.get("set-cookie", "").lower()  # cookie cleared

    assert all(s["revoked_at"] is not None for s in env["repo"].sessions.values())
    assert (await _post(client, "refresh")).status_code == 401
    reused = await _post(client, "password/reset", {"token": token, "new_password": "other pass!!"})
    assert reused.status_code == 400
    old = await _post(client, "login", {"email": EMAIL, "password": PASSWORD})
    assert old.status_code == 401
    assert (
        await _post(client, "login", {"email": EMAIL, "password": NEW_PASSWORD})
    ).status_code == 200

    # Confidentiality: neither the reset secret, passwords nor tokens reach logs.
    output = caplog.text + capsys.readouterr().out
    for secret in (token, PASSWORD, NEW_PASSWORD, access_token):
        assert secret not in output


@pytest.mark.asyncio
async def test_reset_with_weak_password_is_rejected_and_link_stays_valid(env) -> None:
    client = env["client"]
    await _signup(env)
    await _post(client, "password/forgot", {"email": EMAIL})
    token = token_from_email(env["outbox"].sent[-1])

    weak = await _post(client, "password/reset", {"token": token, "new_password": "short"})
    assert weak.status_code == 422
    ok = await _post(client, "password/reset", {"token": token, "new_password": NEW_PASSWORD})
    assert ok.status_code == 200


@pytest.mark.asyncio
async def test_password_change_requires_an_account_token(env) -> None:
    client = env["client"]
    anonymous = (await client.post("/api/v1/auth/anonymous-session")).json()["access_token"]
    body = {"current_password": PASSWORD, "new_password": NEW_PASSWORD}
    refused = await _post(
        client, "password/change", body, {**WEB, "Authorization": f"Bearer {anonymous}"}
    )
    assert refused.status_code == 401
    assert (await _post(client, "password/change", body)).status_code == 401


@pytest.mark.asyncio
async def test_password_change_rotates_session_and_revokes_old_refresh(env) -> None:
    client = env["client"]
    login = await _signup(env)
    old_cookie = client.cookies.get("chisa_refresh")
    headers = {**WEB, "Authorization": f"Bearer {login.json()['access_token']}"}

    wrong = await _post(
        client, "password/change",
        {"current_password": "wrong password!!", "new_password": NEW_PASSWORD}, headers,
    )
    assert wrong.status_code == 401
    changed = await _post(
        client, "password/change",
        {"current_password": PASSWORD, "new_password": NEW_PASSWORD}, headers,
    )
    assert changed.status_code == 200
    assert client.cookies.get("chisa_refresh") != old_cookie
    assert (await _post(client, "refresh")).status_code == 200

    client.cookies.set("chisa_refresh", old_cookie, path="/api/v1/auth")
    assert (await _post(client, "refresh")).status_code == 401


@pytest.mark.asyncio
async def test_email_features_are_disabled_without_email_delivery(env) -> None:
    client = env["client"]
    env["holder"]["dispatcher"] = make_dispatcher(OutboxSender(enabled=False), APP_URL)

    caps = (await client.get("/api/v1/auth/capabilities")).json()
    assert caps["password_registration"] is False
    for path, body in (
        ("register", {"email": EMAIL, "password": PASSWORD}),
        ("verify-email/resend", {"email": EMAIL}),
        ("password/forgot", {"email": EMAIL}),
    ):
        assert (await _post(client, path, body)).status_code == 503, path
    assert env["repo"].accounts == {}


@pytest.mark.asyncio
async def test_google_callback_reports_claim_needed_for_unverified_holder(env) -> None:
    client = env["client"]
    await _post(client, "register", {"email": "senpai@gmail.com", "password": "squatter pw!!"})

    start = await _post(client, "google/start", {"intent": "login"})
    state = parse_qs(urlsplit(start.json()["authorization_url"]).query)["state"][0]
    callback = await client.get(
        "/api/v1/auth/google/callback", params={"code": "good-code", "state": state}
    )
    assert callback.status_code == 303
    assert parse_qs(urlsplit(callback.headers["location"]).query) == {
        "auth_error": ["claim_email"]
    }
    assert env["repo"].identities == {}


@pytest.mark.asyncio
async def test_email_endpoints_are_rate_limited_per_address(env, monkeypatch) -> None:
    keys: list[str] = []

    async def bucket(**kwargs: object) -> tuple[bool, int, float]:
        key = str(kwargs["key"])
        keys.append(key)
        return (not key.startswith("chisa:ratelimit:auth-email-forgot"), 0, 30.0)

    monkeypatch.setattr(redis_service, "consume_token_bucket", bucket)
    response = await _post(env["client"], "password/forgot", {"email": EMAIL})
    assert response.status_code == 429
    assert all("senpai" not in key for key in keys)


@pytest.mark.asyncio
async def test_dispatcher_enforces_global_daily_ceiling_and_fails_closed() -> None:
    outbox = OutboxSender()
    capped = make_dispatcher(outbox, APP_URL, daily_limit=1)
    mail = OutboundAccountEmail(kind="verify_email", to=EMAIL, token="t" * 43)
    assert await capped.deliver(mail) is True
    assert await capped.deliver(mail) is False
    assert len(outbox.sent) == 1

    async def broken_counter(_key: str, _ttl: int) -> int:
        raise ConnectionError("redis unavailable")

    closed = AccountEmailDispatcher(
        sender=outbox,
        public_app_url=APP_URL,
        daily_counter=broken_counter,
        daily_limit=100,
        verification_ttl_hours=24,
        reset_ttl_minutes=30,
    )
    assert await closed.deliver(mail) is False
    assert len(outbox.sent) == 1
