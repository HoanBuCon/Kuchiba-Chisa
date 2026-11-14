"""One running turn per thread, held in Redis so every API worker sees it (MODE-005)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

LOCK_PREFIX = "chat:v2:turn-lock:"
# Longer than a turn may run, so a crashed worker cannot block the thread for good.
LOCK_SECONDS = 45


class RedisTurnLock:
    def __init__(self, redis: Any) -> None:
        self._redis = redis

    async def acquire(self, thread_id: UUID) -> str | None:
        token: str | None = await self._redis.acquire_lock(
            f"{LOCK_PREFIX}{thread_id}", ttl=LOCK_SECONDS
        )
        return token

    async def release(self, thread_id: UUID, token: str) -> None:
        await self._redis.release_lock(f"{LOCK_PREFIX}{thread_id}", token)
