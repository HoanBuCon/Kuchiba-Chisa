"""A-03 cost quotas and the Discord workload → web-account trust boundary."""

from __future__ import annotations

import time
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from jose import jwt

from app.application.security.chat_admission import (
    ChatAdmissionControl,
    ChatQuotaLimits,
    QuotaExceededError,
    QuotaUnavailableError,
    WorkloadTargetDeniedError,
)
from app.config.settings import settings
from app.domain.services.chat_engine import ChatEngineBusyError
from app.domain.value_objects.principal import PrincipalContext
from app.infrastructure.security.jwt_authenticator import AuthenticationError, jwt_authenticator
from app.interface.api.routes import chat, community
from app.interface.api.schemas.chat import ChatRequest
from app.interface.api.schemas.community import CommunityChatRequest

LIMITS = ChatQuotaLimits(
    web_anon_per_subject=3,
    web_anon_per_ip=5,
    web_account_per_subject=4,
    discord_per_subject=3,
    discord_per_guild=4,
    pool_web_anon=8,
    pool_web_account=6,
    pool_discord=6,
)


class MemoryQuotaStore:
    """Same all-or-nothing semantics as the Redis Lua script."""

    def __init__(self) -> None:
        self.counts: dict[str, int] = {}
        self.fail = False

    async def consume_daily_quota(self, keys, limits, ttl):
        if self.fail:
            raise ConnectionError("redis unavailable")
        for index, (key, limit) in enumerate(zip(keys, limits, strict=True), start=1):
            if self.counts.get(key, 0) >= limit:
                return index
        for key in keys:
            self.counts[key] = self.counts.get(key, 0) + 1
        return 0

    async def refund_daily_quota(self, keys):
        for key in keys:
            self.counts[key] = max(0, self.counts.get(key, 0) - 1)


def _admission(store=None, *, accounts=frozenset(), enabled=True):
    async def account_exists(_session, account_id):
        return account_id in accounts

    return ChatAdmissionControl(
        store=store or MemoryQuotaStore(),
        limits=LIMITS,
        enabled=enabled,
        account_exists=account_exists,
        clock=lambda: 1_791_158_400.0,  # fixed UTC day
    )


def web(subject=None, *, account=False) -> PrincipalContext:
    return PrincipalContext(
        subject_id=subject or str(uuid.uuid4()),
        tenant_id=None,
        channel_id=None,
        source="web",
        kind="user",
        scopes=frozenset({"chat:write", "chat:read", "chat:clear"}),
        authentication="account" if account else "anonymous",
    )


def discord(subject=None, guild: str | None = "guild-1", scopes=("chat:write",)):
    return PrincipalContext(
        subject_id=subject or str(uuid.uuid4()),
        tenant_id=guild,
        channel_id="channel-1" if guild else None,
        source="discord",
        kind="workload",
        scopes=frozenset(scopes),
        authentication="workload",
    )


async def _admit_n(admission, principal, ip, n):
    for _ in range(n):
        await admission.admit(principal, ip)


# ── Quota partitioning ──────────────────────────────────────────────────


def test_counters_are_partitioned_by_surface() -> None:
    admission = _admission()
    now = 1_791_158_400.0
    anon = {scope for scope, _, _ in admission.counters(web(), "198.51.100.7", now)}
    account = {scope for scope, _, _ in admission.counters(web(account=True), "198.51.100.7", now)}
    bot = {scope for scope, _, _ in admission.counters(discord(), "172.28.0.20", now)}
    dm = {scope for scope, _, _ in admission.counters(discord(guild=None), None, now)}

    assert anon == {"pool", "subject", "ip"}
    assert account == {"pool", "subject"}
    assert bot == {"pool", "subject", "guild"}  # never the bot's shared IP
    assert dm == {"pool", "subject"}
    keys = [k for _, k, _ in admission.counters(web(), "198.51.100.7", now)]
    assert all("198.51.100.7" not in key for key in keys)  # IPs are hashed


@pytest.mark.asyncio
async def test_per_subject_daily_quota() -> None:
    admission = _admission()
    principal = web()
    await _admit_n(admission, principal, "198.51.100.1", 3)
    with pytest.raises(QuotaExceededError) as error:
        await admission.admit(principal, "198.51.100.1")
    assert error.value.scope == "subject"
    assert 0 < error.value.retry_after <= 86_400
    await admission.admit(web(), "198.51.100.2")  # another subject is unaffected


@pytest.mark.asyncio
async def test_per_ip_quota_stops_rotating_anonymous_sessions() -> None:
    admission = _admission()
    ip = "198.51.100.9"
    for _ in range(5):
        await admission.admit(web(), ip)  # five fresh anonymous subjects
    with pytest.raises(QuotaExceededError) as error:
        await admission.admit(web(), ip)
    assert error.value.scope == "ip"


@pytest.mark.asyncio
async def test_global_pool_quota_and_pools_are_independent() -> None:
    store = MemoryQuotaStore()
    admission = _admission(store)
    for index in range(8):
        await admission.admit(web(), f"198.51.100.{index}")
    with pytest.raises(QuotaExceededError) as error:
        await admission.admit(web(), "198.51.100.200")
    assert error.value.scope == "pool"
    # An exhausted anonymous pool does not block verified accounts or Discord.
    await admission.admit(web(account=True), "198.51.100.200")
    await admission.admit(discord(), None)


@pytest.mark.asyncio
async def test_per_guild_quota_bounds_any_single_public_guild() -> None:
    admission = _admission()
    for _ in range(4):
        await admission.admit(discord(guild="raid-guild"), None)
    with pytest.raises(QuotaExceededError) as error:
        await admission.admit(discord(guild="raid-guild"), None)
    assert error.value.scope == "guild"
    await admission.admit(discord(guild="other-guild"), None)


@pytest.mark.asyncio
async def test_quota_store_failure_fails_closed() -> None:
    store = MemoryQuotaStore()
    store.fail = True
    with pytest.raises(QuotaUnavailableError):
        await _admission(store).admit(web(), "198.51.100.1")


@pytest.mark.asyncio
async def test_rejected_request_does_not_consume_other_counters() -> None:
    store = MemoryQuotaStore()
    admission = _admission(store)
    principal = web()
    await _admit_n(admission, principal, "198.51.100.1", 3)
    snapshot = dict(store.counts)
    with pytest.raises(QuotaExceededError):
        await admission.admit(principal, "198.51.100.1")
    assert store.counts == snapshot


@pytest.mark.asyncio
async def test_refund_restores_quota() -> None:
    admission = _admission()
    principal = web()
    reservations = [await admission.admit(principal, "198.51.100.1") for _ in range(3)]
    await admission.refund(reservations[-1])
    await admission.admit(principal, "198.51.100.1")


@pytest.mark.asyncio
async def test_quota_disabled_admits_without_store() -> None:
    store = MemoryQuotaStore()
    store.fail = True
    assert await _admission(store, enabled=False).admit(web(), None) is None


def test_production_refuses_to_disable_quotas() -> None:
    from pydantic import ValidationError

    from app.config.settings import Settings

    with pytest.raises(ValidationError, match="CHAT_QUOTA_ENABLED"):
        Settings(
            _env_file=None,
            APP_ENV="production",
            SECRET_KEY="a" * 32,
            DATABASE_URL="postgresql+asyncpg://chisa:secret@postgres/chisa_db",
            JWT_SECRET="b" * 32,
            DISCORD_WORKLOAD_JWT_SECRET="c" * 32,
            REDIS_PASSWORD="redis-secret",
            QDRANT_API_KEY="qdrant-secret",
            CHAT_QUOTA_ENABLED=False,
        )


# ── Route integration ───────────────────────────────────────────────────


class DenyingAdmission:
    def __init__(self, error: Exception) -> None:
        self.error = error
        self.refund = AsyncMock()

    async def admit(self, *_args):
        raise self.error

    async def ensure_workload_target_allowed(self, *_args):
        return None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "expected"),
    ((QuotaExceededError("subject", 3600), 429), (QuotaUnavailableError(), 503)),
)
async def test_chat_route_enforces_quota_before_any_llm_work(monkeypatch, error, expected):
    run = AsyncMock()
    monkeypatch.setattr(chat, "_run_chat_request", run)
    with pytest.raises(HTTPException) as raised:
        await chat.chat_endpoint(
            request=ChatRequest(message="hello"),
            http_request=SimpleNamespace(headers={}, state=SimpleNamespace(client_ip="1.2.3.4")),
            principal=web(),
            admission=DenyingAdmission(error),
            session=SimpleNamespace(),
            chat_engine=SimpleNamespace(),
        )
    assert raised.value.status_code == expected
    run.assert_not_awaited()


@pytest.mark.asyncio
async def test_busy_chat_is_refunded(monkeypatch) -> None:
    store = MemoryQuotaStore()
    admission = _admission(store)
    monkeypatch.setattr(chat, "_start_chat_trace", lambda *args: "trace-1")
    monkeypatch.setattr(
        chat, "_run_chat_request", AsyncMock(side_effect=ChatEngineBusyError("u"))
    )
    principal = web()
    with pytest.raises(HTTPException) as raised:
        await chat.chat_endpoint(
            request=ChatRequest(message="hello"),
            http_request=SimpleNamespace(headers={}, state=SimpleNamespace(client_ip="1.2.3.4")),
            principal=principal,
            admission=admission,
            session=SimpleNamespace(),
            chat_engine=SimpleNamespace(),
        )
    assert raised.value.status_code == 429
    assert sum(store.counts.values()) == 0


# ── Concurrency (existing per-subject chat lock) ────────────────────────


@pytest.mark.asyncio
async def test_second_concurrent_chat_for_same_subject_is_rejected() -> None:
    from app.domain.services.chat_engine import ChatEngine

    cache = SimpleNamespace(acquire_lock=AsyncMock(return_value=None))
    engine = ChatEngine.__new__(ChatEngine)
    engine.cache = cache  # lock already held (or Redis down: acquire fails closed)
    with pytest.raises(ChatEngineBusyError):
        await engine.chat_detailed(session=SimpleNamespace(), user_id="u", user_message="hi")
    cache.acquire_lock.assert_awaited_once()
    assert cache.acquire_lock.await_args.args[0] == "chisa:chat_lock:u"


@pytest.mark.asyncio
async def test_redis_lock_acquisition_failure_is_fail_closed(monkeypatch) -> None:
    from app.infrastructure.cache.redis.redis_service import RedisService

    service = RedisService.__new__(RedisService)
    service._client = SimpleNamespace(set=AsyncMock(side_effect=ConnectionError("down")))
    assert await service.acquire_lock("chisa:chat_lock:u", ttl=120) is None


# ── Discord workload trust boundary ─────────────────────────────────────


def _workload_token(scopes: list[str], subject: str = "discord-subject") -> str:
    now = int(time.time())
    claims = {
        "sub": subject,
        "scopes": scopes,
        "token_use": "workload",
        "source": "discord",
        "tenant_id": "guild-1",
        "channel_id": "channel-1",
        "iss": settings.DISCORD_WORKLOAD_JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE,
        "iat": now,
        "exp": now + 120,
    }
    return jwt.encode(claims, settings.DISCORD_WORKLOAD_JWT_SECRET, settings.JWT_ALGORITHM)


@pytest.mark.parametrize(
    "scopes",
    (["chat:read:any"], ["chat:write", "chat:read"], ["ingestion:source:write"], ["admin"]),
)
def test_workload_tokens_cannot_carry_unapproved_scopes(scopes) -> None:
    with pytest.raises(AuthenticationError):
        jwt_authenticator.authenticate_bearer(f"Bearer {_workload_token(scopes)}")


def test_workload_tokens_with_bot_scopes_are_accepted() -> None:
    for scopes in (
        ["chat:write"],
        ["chat:clear"],
        ["chat:clear:any"],
        ["community:write"],
        ["community:clear:self"],
        ["community:clear:any"],
    ):
        principal = jwt_authenticator.authenticate_bearer(f"Bearer {_workload_token(scopes)}")
        assert principal.kind == "workload" and principal.source == "discord"


def test_web_tokens_signed_with_bot_secret_are_rejected() -> None:
    now = int(time.time())
    forged = jwt.encode(
        {
            "sub": "victim", "scopes": ["chat:write"], "token_use": "web", "source": "web",
            "iss": settings.JWT_ISSUER, "aud": settings.JWT_AUDIENCE, "iat": now, "exp": now + 60,
        },
        settings.DISCORD_WORKLOAD_JWT_SECRET,
        settings.JWT_ALGORITHM,
    )
    with pytest.raises(AuthenticationError):
        jwt_authenticator.authenticate_bearer(f"Bearer {forged}")


@pytest.mark.asyncio
async def test_workload_cannot_target_registered_web_account() -> None:
    account_id = uuid.uuid4()
    admission = _admission(accounts=frozenset({account_id}))

    with pytest.raises(WorkloadTargetDeniedError):
        await admission.ensure_workload_target_allowed(
            None, discord(subject=str(account_id)), str(account_id)
        )
    # Discord subjects (bot-minted core_user_id) and web principals are unaffected.
    await admission.ensure_workload_target_allowed(None, discord(), str(uuid.uuid4()))
    await admission.ensure_workload_target_allowed(
        None, web(str(account_id), account=True), str(account_id)
    )


@pytest.mark.asyncio
async def test_chat_clear_and_community_routes_deny_workload_on_web_account(monkeypatch) -> None:
    account_id = str(uuid.uuid4())
    admission = _admission(accounts=frozenset({uuid.UUID(account_id)}))
    run = AsyncMock()
    monkeypatch.setattr(chat, "_run_chat_request", run)

    with pytest.raises(HTTPException) as chat_error:
        await chat.chat_endpoint(
            request=ChatRequest(message="hello"),
            http_request=SimpleNamespace(headers={}),
            principal=discord(subject=account_id),
            admission=admission,
            session=SimpleNamespace(),
            chat_engine=SimpleNamespace(),
        )
    assert chat_error.value.status_code == 403
    run.assert_not_awaited()

    clear_use_case = SimpleNamespace(execute=AsyncMock())
    with pytest.raises(HTTPException) as clear_error:
        await chat.clear_user_memory(
            user_id=account_id,
            principal=discord(scopes=("chat:clear:any",)),
            admission=admission,
            session=SimpleNamespace(),
            clear_use_case=clear_use_case,
        )
    assert clear_error.value.status_code == 403
    clear_use_case.execute.assert_not_awaited()

    engine = SimpleNamespace(community_chat_detailed=AsyncMock())
    with pytest.raises(HTTPException) as community_error:
        await community.community_chat_endpoint(
            request=CommunityChatRequest(message="hello"),
            principal=discord(subject=account_id, scopes=("community:write",)),
            admission=admission,
            session=SimpleNamespace(),
            chat_engine=engine,
        )
    assert community_error.value.status_code == 403
    engine.community_chat_detailed.assert_not_awaited()


@pytest.mark.asyncio
async def test_discord_moderator_erasure_of_discord_subjects_still_works() -> None:
    admission = _admission(accounts=frozenset({uuid.uuid4()}))
    clear_use_case = SimpleNamespace(
        execute=AsyncMock(return_value={"job_id": "j", "status": "completed", "stores": {}})
    )
    discord_member = str(uuid.uuid4())  # bot-minted core_user_id, not a web account
    response = await chat.clear_user_memory(
        user_id=discord_member,
        principal=discord(scopes=("chat:clear:any",)),
        admission=admission,
        session=SimpleNamespace(),
        clear_use_case=clear_use_case,
    )
    assert response["status"] == "ok"
