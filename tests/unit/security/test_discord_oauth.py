"""Discord OAuth: adapter, account policy and HTTP flow (IAM-005, IAM-006), no real network."""

from __future__ import annotations

from collections.abc import AsyncIterator
from urllib.parse import parse_qs, urlsplit

import httpx
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
    get_discord_identity_provider,
    get_google_identity_provider,
)
from app.application.security.accounts import (
    AccountLinkRequiredError,
    EmailClaimRequiredError,
    ExternalIdentityRejectedError,
    LastLoginMethodError,
)
from app.config.settings import settings
from app.domain.interfaces.accounts import IExternalIdentityProvider
from app.domain.models.account import VerifiedExternalIdentity
from app.infrastructure.cache.redis.redis_service import redis_service
from app.infrastructure.database.engine import get_db_session
from app.infrastructure.security.discord_oauth import (
    DISCORD_TOKEN_ENDPOINT,
    DISCORD_USER_ENDPOINT,
    DiscordOAuthProvider,
)
from app.infrastructure.security.google_oidc import ExternalIdentityVerificationError
from app.interface.api.routes import auth
from app.interface.middlewares.rate_limiter import RateLimitMiddleware

PASSWORD = "correct horse battery"
WEB = {"X-Chisa-Client": "web"}
APP_URL = "https://chisa.example.test"
SESSION = object()
REDIRECT = "https://chisa.example.test/api/v1/auth/discord/callback"


def discord(subject: str = "1000000000000001", email="senpai@example.com", verified=True):
    return VerifiedExternalIdentity(
        provider="discord", subject=subject, email=email, email_verified=verified
    )


def google(subject: str = "g-1", email="senpai@gmail.com"):
    return VerifiedExternalIdentity(
        provider="google", subject=subject, email=email, email_verified=True
    )


async def verified_password_account(service, email: str = "senpai@example.com"):
    outbound = await service.register(SESSION, email, PASSWORD)
    await service.verify_email(SESSION, outbound.token)
    return await service.login(SESSION, email, PASSWORD)


# ── Adapter (HTTP mocked) ─────────────────────────────────────────────────


def _adapter(handler) -> DiscordOAuthProvider:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return DiscordOAuthProvider(
        client_id="client-id",
        client_secret="client-secret",
        redirect_uri=REDIRECT,
        http_client=client,
    )


def _discord_api(profile: dict, token_body: dict | None = None, token_status: int = 200):
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == DISCORD_TOKEN_ENDPOINT:
            seen["token_form"] = parse_qs(request.content.decode())
            body = token_body or {
                "access_token": "opaque-access",
                "scope": "identify email",
                "token_type": "Bearer",
            }
            return httpx.Response(token_status, json=body)
        assert str(request.url) == DISCORD_USER_ENDPOINT
        seen["authorization"] = request.headers["authorization"]
        return httpx.Response(200, json=profile)

    return handler, seen


def test_authorization_url_requests_identify_email_with_state_and_pkce() -> None:
    provider = _adapter(lambda request: httpx.Response(500))

    url = provider.authorization_url(state="st", nonce="unused", code_challenge="chal")
    query = parse_qs(urlsplit(url).query)

    assert urlsplit(url).netloc == "discord.com"
    assert query["scope"] == ["identify email"]
    assert query["state"] == ["st"]
    assert query["code_challenge"] == ["chal"] and query["code_challenge_method"] == ["S256"]
    assert query["redirect_uri"] == [REDIRECT] and query["response_type"] == ["code"]
    assert "client-secret" not in url


@pytest.mark.asyncio
async def test_exchange_redeems_code_with_verifier_and_reads_verified_email() -> None:
    handler, seen = _discord_api(
        {"id": "1000000000000001", "email": "senpai@example.com", "verified": True}
    )

    identity = await _adapter(handler).exchange_code(
        code="the-code", code_verifier="the-verifier", nonce="n"
    )

    assert (identity.provider, identity.subject) == ("discord", "1000000000000001")
    assert identity.email == "senpai@example.com" and identity.email_verified is True
    assert seen["token_form"]["code_verifier"] == ["the-verifier"]
    assert seen["token_form"]["grant_type"] == ["authorization_code"]
    assert seen["authorization"] == "Bearer opaque-access"


@pytest.mark.asyncio
@pytest.mark.parametrize("verified", [False, None, "true", 1])
async def test_email_is_verified_only_when_discord_says_exactly_true(verified) -> None:
    handler, _ = _discord_api({"id": "42", "email": "x@example.com", "verified": verified})

    identity = await _adapter(handler).exchange_code(code="c", code_verifier="v", nonce="n")

    assert identity.email_verified is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "profile", [{"email": "x@example.com"}, {"id": "abc"}, {"id": 42}, {"id": "9" * 40}]
)
async def test_a_missing_or_malformed_discord_id_is_rejected(profile) -> None:
    handler, _ = _discord_api(profile)

    with pytest.raises(ExternalIdentityVerificationError):
        await _adapter(handler).exchange_code(code="c", code_verifier="v", nonce="n")


@pytest.mark.asyncio
async def test_a_rejected_code_or_missing_identify_scope_fails() -> None:
    handler, _ = _discord_api({"id": "42"}, token_status=400)
    with pytest.raises(ExternalIdentityVerificationError):
        await _adapter(handler).exchange_code(code="c", code_verifier="v", nonce="n")

    handler, _ = _discord_api({"id": "42"}, token_body={"access_token": "t", "scope": "email"})
    with pytest.raises(ExternalIdentityVerificationError):
        await _adapter(handler).exchange_code(code="c", code_verifier="v", nonce="n")


# ── Account policy ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_verified_discord_identity_creates_a_member_keyed_by_discord_id() -> None:
    repo = InMemoryAccountRepository()
    service = make_service(repo)

    first = await service.sign_in_with_external_identity(SESSION, discord())
    again = await service.sign_in_with_external_identity(SESSION, discord(email="new@example.com"))

    assert again.account.id == first.account.id
    assert first.account.email == "senpai@example.com" and first.account.email_verified
    assert first.account.linked_providers == ("discord",)


@pytest.mark.asyncio
async def test_unverified_discord_email_is_not_trusted_or_stored() -> None:
    repo = InMemoryAccountRepository()
    service = make_service(repo)

    issued = await service.sign_in_with_external_identity(SESSION, discord(verified=False))

    # Sign-in works, but the address is neither stored nor marked verified (IAM-005).
    assert issued.account.email is None and issued.account.email_verified is False
    assert issued.account.linked_providers == ("discord",)
    assert await repo.email_exists("senpai@example.com") is False


@pytest.mark.asyncio
async def test_unverified_discord_email_never_merges_into_an_existing_account() -> None:
    repo = InMemoryAccountRepository()
    service = make_service(repo)
    victim = await verified_password_account(service, "senpai@example.com")

    attacker = await service.sign_in_with_external_identity(
        SESSION, discord(subject="666", email="senpai@example.com", verified=False)
    )

    assert attacker.account.id != victim.account.id
    assert (await repo.get_by_id(victim.account.id)).linked_providers == ()


@pytest.mark.asyncio
async def test_verified_discord_email_collision_requires_explicit_link() -> None:
    repo = InMemoryAccountRepository()
    service = make_service(repo)
    victim = await verified_password_account(service, "senpai@example.com")

    with pytest.raises(AccountLinkRequiredError):
        await service.sign_in_with_external_identity(SESSION, discord())
    assert repo.identities == {}
    assert (await repo.get_by_id(victim.account.id)).linked_providers == ()


@pytest.mark.asyncio
async def test_verified_discord_email_held_by_an_unverified_account_needs_a_claim() -> None:
    repo = InMemoryAccountRepository()
    service = make_service(repo)
    await service.register(SESSION, "senpai@example.com", PASSWORD)

    with pytest.raises(EmailClaimRequiredError):
        await service.sign_in_with_external_identity(SESSION, discord())
    assert repo.identities == {}


@pytest.mark.asyncio
async def test_signed_in_account_links_discord_explicitly() -> None:
    repo = InMemoryAccountRepository()
    service = make_service(repo)
    owner = await verified_password_account(service)

    linked = await service.sign_in_with_external_identity(
        SESSION, discord(email="other@example.com"), link_to_account_id=owner.account.id
    )

    assert linked.account.id == owner.account.id
    assert linked.account.linked_providers == ("discord",)
    via_discord = await service.sign_in_with_external_identity(SESSION, discord())
    assert via_discord.account.id == owner.account.id


@pytest.mark.asyncio
async def test_identity_owned_by_another_account_cannot_be_linked() -> None:
    repo = InMemoryAccountRepository()
    service = make_service(repo)
    await service.sign_in_with_external_identity(SESSION, discord())
    other = await verified_password_account(service, "other@example.com")

    with pytest.raises(ExternalIdentityRejectedError):
        await service.sign_in_with_external_identity(
            SESSION, discord(), link_to_account_id=other.account.id
        )
    assert (await repo.get_by_id(other.account.id)).linked_providers == ()


@pytest.mark.asyncio
async def test_unlinking_removes_only_that_provider() -> None:
    repo = InMemoryAccountRepository()
    service = make_service(repo)
    owner = await verified_password_account(service)
    await service.sign_in_with_external_identity(
        SESSION, discord(), link_to_account_id=owner.account.id
    )

    account = await service.unlink_external_identity(SESSION, owner.account.id, "discord")

    assert account.linked_providers == () and account.has_password
    assert repo.identities == {}


@pytest.mark.asyncio
async def test_the_last_login_method_cannot_be_unlinked() -> None:
    repo = InMemoryAccountRepository()
    service = make_service(repo)
    only_discord = await service.sign_in_with_external_identity(SESSION, discord())

    with pytest.raises(LastLoginMethodError):
        await service.unlink_external_identity(SESSION, only_discord.account.id, "discord")
    assert ("discord", "1000000000000001") in repo.identities


@pytest.mark.asyncio
async def test_a_password_that_cannot_log_in_does_not_count_as_a_method() -> None:
    repo = InMemoryAccountRepository()
    service = make_service(repo)
    issued = await service.sign_in_with_external_identity(SESSION, discord(verified=False))
    # A password account whose e-mail is unverified cannot sign in, so it is no fallback.
    repo.accounts[issued.account.id].password_hash = "$2b$12$placeholder"

    with pytest.raises(LastLoginMethodError):
        await service.unlink_external_identity(SESSION, issued.account.id, "discord")


@pytest.mark.asyncio
async def test_unlinking_a_provider_that_is_not_linked_is_rejected() -> None:
    repo = InMemoryAccountRepository()
    service = make_service(repo)
    owner = await verified_password_account(service)

    with pytest.raises(ExternalIdentityRejectedError):
        await service.unlink_external_identity(SESSION, owner.account.id, "discord")


# ── HTTP flow ─────────────────────────────────────────────────────────────


class FakeDiscordProvider(IExternalIdentityProvider):
    def __init__(self) -> None:
        self.identity = discord()
        self.last_verifier: str | None = None

    @property
    def provider(self):
        return "discord"

    def authorization_url(self, *, state: str, nonce: str, code_challenge: str) -> str:
        return f"https://discord.com/oauth2/authorize?state={state}&code_challenge={code_challenge}"

    async def exchange_code(self, *, code: str, code_verifier: str, nonce: str):
        if code != "good-code":
            raise RuntimeError("rejected")
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
    provider = FakeDiscordProvider()
    outbox = OutboxSender()
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware)
    app.include_router(auth.router, prefix="/api/v1")

    async def fake_session() -> AsyncIterator[FakeDbSession]:
        yield FakeDbSession()

    app.dependency_overrides[get_db_session] = fake_session
    app.dependency_overrides[get_account_auth_service] = lambda: make_service(repo)
    app.dependency_overrides[get_discord_identity_provider] = lambda: provider
    app.dependency_overrides[get_google_identity_provider] = lambda: None
    dispatcher = make_dispatcher(outbox, APP_URL)
    app.dependency_overrides[get_account_email_dispatcher] = lambda: dispatcher
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://testserver"
    ) as client:
        yield {"client": client, "repo": repo, "provider": provider, "outbox": outbox}


async def signup(env: dict, email: str = "senpai@example.com"):
    client = env["client"]
    await client.post(
        "/api/v1/auth/register", json={"email": email, "password": PASSWORD}, headers=WEB
    )
    token = token_from_email(env["outbox"].sent[-1])
    await client.post("/api/v1/auth/verify-email", json={"token": token}, headers=WEB)
    return await client.post(
        "/api/v1/auth/login", json={"email": email, "password": PASSWORD}, headers=WEB
    )


async def _start(client: AsyncClient, intent: str = "login", token: str | None = None) -> str:
    headers = dict(WEB)
    if token:
        headers["Authorization"] = f"Bearer {token}"
    response = await client.post(
        "/api/v1/auth/discord/start", json={"intent": intent}, headers=headers
    )
    assert response.status_code == 200, response.text
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie and "path=/api/v1/auth/discord" in cookie
    return parse_qs(urlsplit(response.json()["authorization_url"]).query)["state"][0]


def _redirect_params(response) -> dict[str, list[str]]:
    assert response.status_code == 303
    assert response.headers["location"].startswith(APP_URL + "/")
    return parse_qs(urlsplit(response.headers["location"]).query)


@pytest.mark.asyncio
async def test_discord_login_creates_account_and_sets_session_cookie(env) -> None:
    client = env["client"]
    state = await _start(client)

    callback = await client.get(
        "/api/v1/auth/discord/callback", params={"code": "good-code", "state": state}
    )

    assert _redirect_params(callback) == {"auth": ["discord"]}
    assert "chisa_refresh=" in callback.headers.get("set-cookie", "")
    assert env["provider"].last_verifier and len(env["provider"].last_verifier) >= 43
    session = await client.post("/api/v1/auth/refresh", headers=WEB)
    assert session.json()["account"]["providers"] == ["discord"]


@pytest.mark.asyncio
async def test_discord_callback_rejects_a_state_mismatch_without_creating_accounts(env) -> None:
    client = env["client"]
    no_transaction = await client.get(
        "/api/v1/auth/discord/callback", params={"code": "good-code", "state": "x"}
    )
    assert _redirect_params(no_transaction) == {"auth_error": ["expired"]}

    await _start(client)
    forged = await client.get(
        "/api/v1/auth/discord/callback", params={"code": "good-code", "state": "attacker-state"}
    )
    assert _redirect_params(forged) == {"auth_error": ["state"]}
    assert env["repo"].accounts == {}


@pytest.mark.asyncio
async def test_a_google_transaction_cookie_is_not_sent_to_the_discord_callback(env) -> None:
    client = env["client"]
    client._transport.app.dependency_overrides[get_google_identity_provider] = (
        lambda: FakeDiscordProvider()
    )
    started = await client.post("/api/v1/auth/google/start", json={}, headers=WEB)
    state = parse_qs(urlsplit(started.json()["authorization_url"]).query)["state"][0]

    callback = await client.get(
        "/api/v1/auth/discord/callback", params={"code": "good-code", "state": state}
    )

    assert _redirect_params(callback) == {"auth_error": ["expired"]}


@pytest.mark.asyncio
async def test_signed_in_account_links_then_unlinks_discord_over_http(env) -> None:
    client = env["client"]
    token = (await signup(env)).json()["access_token"]
    owner_id = next(iter(env["repo"].accounts))
    state = await _start(client, "link", token)

    callback = await client.get(
        "/api/v1/auth/discord/callback", params={"code": "good-code", "state": state}
    )
    assert _redirect_params(callback) == {"auth": ["discord"]}
    assert env["repo"].identities == {("discord", "1000000000000001"): owner_id}

    unlinked = await client.delete(
        "/api/v1/auth/identities/discord", headers={**WEB, "Authorization": f"Bearer {token}"}
    )
    assert unlinked.status_code == 200 and unlinked.json()["providers"] == []
    assert env["repo"].identities == {}


@pytest.mark.asyncio
async def test_unlinking_the_only_login_method_returns_conflict(env) -> None:
    client = env["client"]
    state = await _start(client)
    await client.get("/api/v1/auth/discord/callback", params={"code": "good-code", "state": state})
    token = (await client.post("/api/v1/auth/refresh", headers=WEB)).json()["access_token"]

    refused = await client.delete(
        "/api/v1/auth/identities/discord", headers={**WEB, "Authorization": f"Bearer {token}"}
    )

    assert refused.status_code == 409
    assert len(env["repo"].identities) == 1


@pytest.mark.asyncio
async def test_unlink_needs_the_client_header_and_an_account_token(env) -> None:
    client = env["client"]
    anonymous = (await client.post("/api/v1/auth/anonymous-session")).json()["access_token"]

    no_header = await client.delete("/api/v1/auth/identities/discord")
    anonymous_token = await client.delete(
        "/api/v1/auth/identities/discord", headers={**WEB, "Authorization": f"Bearer {anonymous}"}
    )

    assert no_header.status_code == 403
    assert anonymous_token.status_code == 401


@pytest.mark.asyncio
async def test_discord_unavailable_when_not_configured(env) -> None:
    client = env["client"]
    client._transport.app.dependency_overrides[get_discord_identity_provider] = lambda: None

    response = await client.post("/api/v1/auth/discord/start", json={}, headers=WEB)

    assert response.status_code == 503
