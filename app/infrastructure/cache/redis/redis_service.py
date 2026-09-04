from __future__ import annotations

import json
from collections.abc import Awaitable
from typing import Any, TypeVar, cast

import redis.asyncio as aioredis

from app.config.settings import settings
from app.infrastructure.logging.logger import get_logger

log = get_logger(__name__)

T = TypeVar("T")

# ─── Redis Connection Pool ─────────────────────────────────────────────────────

_redis_pool: aioredis.ConnectionPool | None = None


def _get_pool() -> aioredis.ConnectionPool:
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = aioredis.ConnectionPool.from_url(
            settings.REDIS_URL,
            password=settings.REDIS_PASSWORD or None,
            username=settings.REDIS_USERNAME,
            max_connections=50,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
            retry_on_timeout=True,
        )
    return _redis_pool


def get_redis_client() -> aioredis.Redis:
    """Returns an async Redis client from the shared connection pool."""
    return aioredis.Redis(connection_pool=_get_pool())


# ─── Redis Service ─────────────────────────────────────────────────────────────

from app.domain.interfaces.cache_provider import ICacheProvider


class RedisService(ICacheProvider):
    """
    Async Redis service providing typed operations for all caching needs.
    All methods operate on the shared connection pool — no persistent connection held.
    """

    def __init__(self) -> None:
        self._client = get_redis_client()

    # ── Health ────────────────────────────────────────────────────
    async def health_check(self) -> bool:
        try:
            result = await self._client.ping()
            return result is True or result == b"PONG" or result == "PONG"
        except Exception as e:
            log.error("Redis health check failed", error=str(e))
            return False

    # ── String / JSON ─────────────────────────────────────────────
    async def get(self, key: str) -> str | None:
        return await self._client.get(key)  # type: ignore[return-value]

    async def set(self, key: str, value: str, ttl: int | None = None) -> None:
        if ttl:
            await self._client.set(key, value, ex=ttl)
        else:
            await self._client.set(key, value)

    async def get_json(self, key: str) -> Any | None:
        raw = await self.get(key)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            log.warning("Failed to decode Redis JSON value", key=key)
            return None

    async def set_json(self, key: str, value: Any, ttl: int | None = None) -> None:
        await self.set(key, json.dumps(value, default=str), ttl)

    async def delete(self, key: str) -> None:
        await self._client.delete(key)

    async def delete_pattern(self, pattern: str) -> int:
        deleted = 0
        try:
            async for key in self._client.scan_iter(match=pattern, count=100):
                await self._client.delete(key)
                deleted += 1
        except Exception as e:
            log.warning("Failed to delete pattern in Redis", pattern=pattern, error=str(e))
        return deleted

    async def exists(self, key: str) -> bool:
        result = await self._client.exists(key)
        return bool(result)

    async def expire(self, key: str, ttl: int) -> None:
        await self._client.expire(key, ttl)

    async def incr(self, key: str) -> int:
        return await cast(Awaitable[int], self._client.incr(key))

    async def consume_token_bucket(
        self,
        *,
        key: str,
        capacity: int,
        refill_period_seconds: int,
        now: float,
    ) -> tuple[bool, int, float]:
        """Atomically consume one token from a Redis-backed token bucket."""
        script = """
        local values = redis.call('HMGET', KEYS[1], 'tokens', 'updated_at')
        local tokens = tonumber(values[1]) or tonumber(ARGV[1])
        local updated_at = tonumber(values[2]) or tonumber(ARGV[3])
        local capacity = tonumber(ARGV[1])
        local refill_per_second = capacity / tonumber(ARGV[2])
        local now = tonumber(ARGV[3])
        tokens = math.min(capacity, tokens + math.max(0, now - updated_at) * refill_per_second)
        local allowed = 0
        local retry_after = 0
        if tokens >= 1 then
            tokens = tokens - 1
            allowed = 1
        else
            retry_after = (1 - tokens) / refill_per_second
        end
        redis.call('HMSET', KEYS[1], 'tokens', tokens, 'updated_at', now)
        redis.call('EXPIRE', KEYS[1], tonumber(ARGV[2]) + 5)
        return {allowed, math.floor(tokens), retry_after}
        """
        result = await cast(
            Awaitable[Any],
            self._client.eval(
                script,
                1,
                key,
                str(capacity),
                str(refill_period_seconds),
                str(now),
            ),
        )
        if not isinstance(result, list) or len(result) != 3:
            raise RuntimeError("Redis token bucket returned an invalid result")
        allowed, remaining, retry_after = (str(value) for value in result)
        return bool(int(allowed)), int(remaining), float(retry_after)

    # ── List (Short-Term Memory) ───────────────────────────────────
    async def lpush(self, key: str, *values: str) -> int:
        return await cast(Awaitable[int], self._client.lpush(key, *values))

    async def lrange(self, key: str, start: int, stop: int) -> list[str]:
        return await cast(Awaitable[list[str]], self._client.lrange(key, start, stop))

    async def ltrim(self, key: str, start: int, stop: int) -> None:
        await cast(Awaitable[str], self._client.ltrim(key, start, stop))

    # ── Distributed Lock (Safe Token-based with Lua Script) ────────
    _RELEASE_LOCK_LUA = """
    if redis.call("get", KEYS[1]) == ARGV[1] then
        return redis.call("del", KEYS[1])
    else
        return 0
    end
    """

    async def acquire_lock(
        self, lock_key: str, ttl: int = 5, token: str | None = None
    ) -> str | None:
        """
        Acquires a distributed lock using a unique token to prevent race conditions.
        Returns the token string if acquired (truthy), or None/empty if failed.
        """
        import uuid
        lock_token = token or str(uuid.uuid4())
        try:
            result = await self._client.set(lock_key, lock_token, ex=ttl, nx=True)
            if result is True:
                return lock_token
            return None
        except Exception as e:
            log.warning("Redis acquire_lock failed, proceeding without lock (fail-open)", lock_key=lock_key, error=str(e))
            return lock_token

    async def release_lock(self, lock_key: str, token: str | None = None) -> bool:
        """
        Safely releases the distributed lock only if the token matches, preventing accidental deletion of others' locks.
        """
        try:
            if token:
                res = await cast(
                    Awaitable[Any], self._client.eval(self._RELEASE_LOCK_LUA, 1, lock_key, token)
                )
                return bool(res)
            else:
                await self._client.delete(lock_key)
                return True
        except Exception as e:
            log.warning("Redis release_lock failed, ignoring", lock_key=lock_key, error=str(e))
            return False

    # ── Connection Management ────────────────────────────────────
    async def disconnect(self) -> None:
        await self._client.aclose()
        log.info("Redis client disconnected")


# ── Module-level singleton ───────────────────────────────────────────
redis_service = RedisService()
