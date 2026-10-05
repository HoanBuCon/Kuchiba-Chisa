"""A-03 quota primitives against the isolated Redis (atomicity, TTL, refund)."""

from __future__ import annotations

import uuid

import pytest
import redis.asyncio as aioredis

from app.application.security.chat_admission import (
    ChatAdmissionControl,
    ChatQuotaLimits,
    QuotaExceededError,
)
from app.config.settings import settings
from app.domain.value_objects.principal import PrincipalContext
from app.infrastructure.cache.redis.redis_service import RedisService


def _redis() -> RedisService:
    """A client bound to this test's event loop (the module singleton is not)."""
    service = RedisService()
    service._client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    return service


def _keys(n: int) -> list[str]:
    run = uuid.uuid4().hex
    return [f"chisa:quota:test:{run}:{i}" for i in range(n)]


@pytest.mark.asyncio
async def test_consume_is_all_or_nothing_with_ttl_and_refund() -> None:
    redis = _redis()
    keys = _keys(2)
    try:
        assert await redis.consume_daily_quota(keys, [5, 1], 120) == 0
        # Second key is full: refused, and the first key is NOT incremented.
        assert await redis.consume_daily_quota(keys, [5, 1], 120) == 2
        assert await redis.get(keys[0]) == "1"
        assert 0 < await redis._client.ttl(keys[0]) <= 120

        await redis.refund_daily_quota(keys)
        assert await redis.get(keys[0]) == "0"
        assert await redis.consume_daily_quota(keys, [5, 1], 120) == 0
    finally:
        await redis._client.delete(*keys)


@pytest.mark.asyncio
async def test_incr_with_ttl_sets_expiry_once() -> None:
    redis = _redis()
    (key,) = _keys(1)
    try:
        assert await redis.incr_with_ttl(key, 60) == 1
        assert await redis.incr_with_ttl(key, 60) == 2
        assert 0 < await redis._client.ttl(key) <= 60
    finally:
        await redis._client.delete(key)


@pytest.mark.asyncio
async def test_admission_against_real_redis_enforces_per_subject_limit() -> None:
    redis = _redis()
    limits = ChatQuotaLimits(
        web_anon_per_subject=2, web_anon_per_ip=100, web_account_per_subject=5,
        discord_per_subject=5, discord_per_guild=50,
        pool_web_anon=10_000, pool_web_account=10_000, pool_discord=10_000,
    )

    async def never(_session, _id):
        return False

    admission = ChatAdmissionControl(
        store=redis, limits=limits, enabled=True, account_exists=never
    )
    principal = PrincipalContext(
        subject_id=str(uuid.uuid4()), tenant_id=None, channel_id=None,
        source="web", kind="user", scopes=frozenset({"chat:write"}),
    )
    ip = f"203.0.113.{uuid.uuid4().int % 250}"
    reservations = [await admission.admit(principal, ip) for _ in range(2)]
    try:
        with pytest.raises(QuotaExceededError) as error:
            await admission.admit(principal, ip)
        assert error.value.scope == "subject"
    finally:
        for reservation in reservations:
            await admission.refund(reservation)
