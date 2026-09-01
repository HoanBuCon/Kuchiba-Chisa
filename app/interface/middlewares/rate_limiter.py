"""Trusted-principal token-bucket rate limiting for expensive API routes."""

from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import time
from dataclasses import dataclass

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse
from starlette.types import ASGIApp

from app.config.settings import settings
from app.domain.value_objects.principal import PrincipalContext
from app.infrastructure.cache.redis.redis_service import redis_service
from app.infrastructure.logging.logger import get_logger
from app.infrastructure.security.jwt_authenticator import AuthenticationError, jwt_authenticator

log = get_logger(__name__)


@dataclass(slots=True)
class _LocalBucket:
    tokens: float
    updated_at: float


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Enforces a Redis token bucket keyed only by a verified principal.

    Redis is the distributed authority. If it is unavailable, a bounded,
    process-local token bucket preserves abuse protection rather than allowing
    unlimited traffic. Forwarded identity and IP headers are intentionally not
    accepted as rate-limit identities.
    """

    RATE_LIMITED_PREFIXES = ("/api/v1/chat", "/api/v1/community")
    ANONYMOUS_SESSION_PATH = "/api/v1/auth/anonymous-session"

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)
        self._local_buckets: dict[str, _LocalBucket] = {}
        self._local_lock = asyncio.Lock()
        self._trusted_proxy_networks = self._parse_trusted_proxy_networks()

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        path = request.url.path
        if path == self.ANONYMOUS_SESSION_PATH:
            client_ip = self._trusted_client_ip(request)
            allowed, _, reset_at = await self._check_anonymous_session_rate(client_ip)
            if not allowed:
                return self._limited_response(reset_at)
            return await call_next(request)

        if not any(path.startswith(prefix) for prefix in self.RATE_LIMITED_PREFIXES):
            return await call_next(request)

        try:
            principal = jwt_authenticator.authenticate_bearer(request.headers.get("Authorization"))
        except AuthenticationError:
            return JSONResponse(
                status_code=401,
                content={"detail": "Authentication required"},
                headers={"WWW-Authenticate": "Bearer"},
            )
        request.state.principal = principal

        client_ip = self._trusted_client_ip(request)
        anomaly_allowed, _, anomaly_reset_at = await self._check_ip_anomaly(client_ip)
        if not anomaly_allowed:
            return self._limited_response(anomaly_reset_at)

        allowed, remaining, reset_at = await self._check_rate(principal, request.method, path)
        if not allowed:
            retry_after = max(1, int(reset_at - time.time()))
            log.warning(
                "Rate limit exceeded",
                principal_id=principal.subject_id,
                tenant_id=principal.tenant_id,
                route=path,
                retry_after=retry_after,
            )
            return self._limited_response(reset_at)

        response = await call_next(request)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(int(reset_at))
        response.headers["X-RateLimit-Limit"] = str(settings.RATE_LIMIT_PER_MINUTE)
        return response

    @staticmethod
    def _limited_response(reset_at: float) -> JSONResponse:
        retry_after = max(1, int(reset_at - time.time()))
        return JSONResponse(
            status_code=429,
            content={"detail": "Rate limit exceeded", "retry_after": retry_after},
            headers={
                "Retry-After": str(retry_after),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(int(reset_at)),
            },
        )

    @staticmethod
    def _rate_limit_key(principal: PrincipalContext, method: str, path: str) -> str:
        route = RateLimitMiddleware._route_bucket(method, path)
        raw_key = "|".join(
            (principal.subject_id, principal.tenant_id or "-", route)
        )
        digest = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
        return f"chisa:ratelimit:v2:{digest}"

    @staticmethod
    def _ip_anomaly_key(client_ip: str) -> str:
        """Return the independent, privacy-preserving IP anomaly bucket key.

        The primary quota is intentionally scoped to principal, tenant, and
        route.  This secondary bucket must *not* include a principal so a
        caller cannot evade the network-level control by rotating otherwise
        valid anonymous sessions or workload subjects.
        """
        raw_key = "|".join(("ip", client_ip))
        digest = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
        return f"chisa:ratelimit:ip:v1:{digest}"

    @staticmethod
    def _anonymous_session_key(client_ip: str) -> str:
        """Pre-auth exception: only a trusted network address is available."""
        digest = hashlib.sha256(f"anonymous-session|{client_ip}".encode()).hexdigest()
        return f"chisa:ratelimit:anonymous-session:v1:{digest}"

    @staticmethod
    def _parse_trusted_proxy_networks() -> tuple[
        ipaddress.IPv4Network | ipaddress.IPv6Network, ...
    ]:
        values = (value.strip() for value in settings.TRUSTED_PROXY_CIDRS.split(","))
        return tuple(ipaddress.ip_network(value, strict=False) for value in values if value)

    def _trusted_client_ip(self, request: Request) -> str:
        peer_ip = request.client.host if request.client else "unknown"
        try:
            peer_address = ipaddress.ip_address(peer_ip)
        except ValueError:
            return peer_ip
        if not any(peer_address in network for network in self._trusted_proxy_networks):
            return peer_ip
        forwarded = request.headers.get("X-Forwarded-For", "")
        candidate = forwarded.split(",", maxsplit=1)[0].strip()
        try:
            return str(ipaddress.ip_address(candidate))
        except ValueError:
            return peer_ip

    @staticmethod
    def _route_bucket(method: str, path: str) -> str:
        """Collapse path parameters so they cannot create quota bypass keys."""
        if path.startswith("/api/v1/chat/history/"):
            return "GET:chat.history"
        if path.startswith("/api/v1/chat/emotions/"):
            return "GET:chat.emotions"
        if path.startswith("/api/v1/chat/clear/"):
            return "DELETE:chat.clear"
        if path == "/api/v1/chat/stream":
            return "POST:chat.stream"
        if path == "/api/v1/chat":
            return "POST:chat"
        if path.startswith("/api/v1/community/clear/"):
            return "DELETE:community.clear"
        if path == "/api/v1/community/chat":
            return "POST:community.chat"
        return f"{method.upper()}:{path}"

    async def _check_rate(
        self, principal: PrincipalContext, method: str, path: str
    ) -> tuple[bool, int, float]:
        key = self._rate_limit_key(principal, method, path)
        capacity = settings.RATE_LIMIT_PER_MINUTE
        now = time.time()
        try:
            allowed, remaining, retry_after = await redis_service.consume_token_bucket(
                key=key,
                capacity=capacity,
                refill_period_seconds=60,
                now=now,
            )
            return allowed, remaining, now + retry_after
        except Exception as error:
            log.warning(
                "Redis rate limit unavailable; using bounded local limiter",
                error_type=type(error).__name__,
            )
            return await self._check_local_bucket(key, capacity, now)

    async def _check_ip_anomaly(self, client_ip: str) -> tuple[bool, int, float]:
        return await self._check_bucket(
            self._ip_anomaly_key(client_ip),
            settings.RATE_LIMIT_IP_ANOMALY_PER_MINUTE,
        )

    async def _check_anonymous_session_rate(self, client_ip: str) -> tuple[bool, int, float]:
        return await self._check_bucket(
            self._anonymous_session_key(client_ip),
            settings.ANONYMOUS_SESSION_RATE_LIMIT_PER_MINUTE,
        )

    async def _check_bucket(self, key: str, capacity: int) -> tuple[bool, int, float]:
        now = time.time()
        try:
            allowed, remaining, retry_after = await redis_service.consume_token_bucket(
                key=key,
                capacity=capacity,
                refill_period_seconds=60,
                now=now,
            )
            return allowed, remaining, now + retry_after
        except Exception as error:
            log.warning(
                "Redis rate limit unavailable; using bounded local limiter",
                error_type=type(error).__name__,
            )
            return await self._check_local_bucket(key, capacity, now)

    async def _check_local_bucket(
        self, key: str, capacity: int, now: float
    ) -> tuple[bool, int, float]:
        refill_rate = capacity / 60.0
        async with self._local_lock:
            bucket = self._local_buckets.get(key)
            if bucket is None:
                if len(self._local_buckets) >= settings.RATE_LIMIT_LOCAL_FALLBACK_MAX_KEYS:
                    oldest_key = min(
                        self._local_buckets, key=lambda item: self._local_buckets[item].updated_at
                    )
                    self._local_buckets.pop(oldest_key, None)
                bucket = _LocalBucket(tokens=float(capacity), updated_at=now)
                self._local_buckets[key] = bucket

            elapsed = max(0.0, now - bucket.updated_at)
            bucket.tokens = min(float(capacity), bucket.tokens + elapsed * refill_rate)
            bucket.updated_at = now
            if bucket.tokens < 1:
                retry_after = (1 - bucket.tokens) / refill_rate
                return False, 0, now + retry_after
            bucket.tokens -= 1
            return True, int(bucket.tokens), now
