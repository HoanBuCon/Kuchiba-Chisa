from __future__ import annotations

import json
from typing import Any, Optional, TypeVar

import redis.asyncio as aioredis

from app.config.settings import settings
from app.infrastructure.logging.logger import get_logger

log = get_logger(__name__)

T = TypeVar("T")

# ─── Redis Connection Pool ─────────────────────────────────────────────────────

_redis_pool: Optional[aioredis.ConnectionPool] = None


def _get_pool() -> aioredis.ConnectionPool:
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = aioredis.ConnectionPool.from_url(
            settings.REDIS_URL,
            password=settings.REDIS_PASSWORD or None,
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
    async def get(self, key: str) -> Optional[str]:
        return await self._client.get(key)  # type: ignore[return-value]

    async def set(self, key: str, value: str, ttl: Optional[int] = None) -> None:
        if ttl:
            await self._client.set(key, value, ex=ttl)
        else:
            await self._client.set(key, value)

    async def get_json(self, key: str) -> Optional[Any]:
        raw = await self.get(key)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            log.warning("Failed to decode Redis JSON value", key=key)
            return None

    async def set_json(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        await self.set(key, json.dumps(value, default=str), ttl)

    async def delete(self, key: str) -> None:
        await self._client.delete(key)

    async def exists(self, key: str) -> bool:
        result = await self._client.exists(key)
        return bool(result)

    async def expire(self, key: str, ttl: int) -> None:
        await self._client.expire(key, ttl)

    async def incr(self, key: str) -> int:
        return await self._client.incr(key)  # type: ignore[return-value]

    # ── List (Short-Term Memory) ───────────────────────────────────
    async def lpush(self, key: str, *values: str) -> int:
        return await self._client.lpush(key, *values)  # type: ignore[return-value]

    async def lrange(self, key: str, start: int, stop: int) -> list[str]:
        return await self._client.lrange(key, start, stop)  # type: ignore[return-value]

    async def ltrim(self, key: str, start: int, stop: int) -> None:
        await self._client.ltrim(key, start, stop)

    # ── Distributed Lock ──────────────────────────────────────────
    async def acquire_lock(self, lock_key: str, ttl: int = 5) -> bool:
        try:
            result = await self._client.set(lock_key, "1", ex=ttl, nx=True)
            return result is True
        except Exception as e:
            log.warning("Redis acquire_lock failed, proceeding without lock (fail-open)", lock_key=lock_key, error=str(e))
            return True

    async def release_lock(self, lock_key: str) -> None:
        try:
            await self._client.delete(lock_key)
        except Exception as e:
            log.warning("Redis release_lock failed, ignoring", lock_key=lock_key, error=str(e))

    # ── Connection Management ────────────────────────────────────
    async def disconnect(self) -> None:
        await self._client.aclose()
        log.info("Redis client disconnected")


# ── Module-level singleton ───────────────────────────────────────────
redis_service = RedisService()
