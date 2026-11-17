"""Short-lived Redis copy of an account's authority, sparing the database (IAM-003)."""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from redis.exceptions import RedisError

from app.domain.interfaces.authz import IAuthzSnapshotCache
from app.domain.models.rbac import (
    PERMISSIONS_VERSION,
    SNAPSHOT_TTL_SECONDS,
    AuthzSnapshot,
    Permission,
)

_log = logging.getLogger(__name__)
KEY_PREFIX = "authz:snapshot:"


class RedisAuthzSnapshotCache(IAuthzSnapshotCache):
    """Every Redis failure degrades to a miss: authority is then read from the database."""

    def __init__(self, redis: Any) -> None:
        self._redis = redis

    async def get(self, account_id: uuid.UUID) -> AuthzSnapshot | None:
        try:
            raw = await self._redis.get(f"{KEY_PREFIX}{account_id}")
            return _decode(raw) if raw else None
        except (RedisError, OSError) as error:
            _log.warning("Authz cache read failed", extra={"failure_class": type(error).__name__})
            return None

    async def set(self, account_id: uuid.UUID, snapshot: AuthzSnapshot) -> None:
        payload = {
            "pv": PERMISSIONS_VERSION,
            "ver": snapshot.authz_ver,
            "perms": sorted(permission.value for permission in snapshot.permissions),
        }
        try:
            await self._redis.set(
                f"{KEY_PREFIX}{account_id}", json.dumps(payload), ttl=SNAPSHOT_TTL_SECONDS
            )
        except (RedisError, OSError) as error:
            _log.warning("Authz cache write failed", extra={"failure_class": type(error).__name__})

    async def invalidate(self, account_id: uuid.UUID) -> None:
        try:
            await self._redis.delete(f"{KEY_PREFIX}{account_id}")
        except (RedisError, OSError) as error:
            # The entry still expires within SNAPSHOT_TTL_SECONDS.
            _log.warning("Authz cache purge failed", extra={"failure_class": type(error).__name__})


def _decode(raw: str) -> AuthzSnapshot | None:
    try:
        payload = json.loads(raw)
        if payload["pv"] != PERMISSIONS_VERSION:
            return None
        return AuthzSnapshot(
            int(payload["ver"]), frozenset(Permission(value) for value in payload["perms"])
        )
    except (ValueError, KeyError, TypeError):
        return None
