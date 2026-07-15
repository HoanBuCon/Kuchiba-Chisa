"""
Redis-backed rate limiting middleware for FastAPI.

Uses a sliding window counter per user_id (or IP fallback) to enforce
request rate limits. Prevents LLM API quota exhaustion from spam.
"""
from __future__ import annotations

import time

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse

from app.config.settings import settings
from app.infrastructure.cache.redis.redis_service import redis_service
from app.infrastructure.logging.logger import get_logger

log = get_logger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Per-user rate limiter using Redis counters with sliding window.
    Only applies to /api/v1/chat endpoints (the expensive LLM-calling paths).
    Health checks and static assets are exempt.
    """

    # Paths that trigger rate limiting (prefix match)
    RATE_LIMITED_PREFIXES = ("/api/v1/chat",)
    USER_ID_HEADER = "X-User-ID"

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # Only rate-limit specific paths
        path = request.url.path
        if not any(path.startswith(prefix) for prefix in self.RATE_LIMITED_PREFIXES):
            return await call_next(request)

        # Never consume request.body() here. BaseHTTPMiddleware forwards the
        # request downstream, where FastAPI must still be able to parse it.
        user_key = self._extract_user_key(request)

        # Check rate limit
        allowed, remaining, reset_at = await self._check_rate(user_key)

        if not allowed:
            retry_after = max(1, int(reset_at - time.time()))
            log.warning(
                "Rate limit exceeded",
                user_key=user_key,
                path=path,
                retry_after=retry_after,
            )
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Rate limit exceeded. Chisa cần nghỉ ngơi một chút, Senpai thử lại sau nhé~",
                    "retry_after": retry_after,
                },
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(reset_at)),
                },
            )

        response = await call_next(request)

        # Add rate limit headers to successful responses
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(int(reset_at))
        response.headers["X-RateLimit-Limit"] = str(settings.RATE_LIMIT_PER_MINUTE)

        return response

    @classmethod
    def _extract_user_key(cls, request: Request) -> str:
        """
        Return a stable rate-limit key without reading the request body.

        Clients should send ``X-User-ID`` for a per-user quota. Requests from
        legacy clients are safely limited by their forwarded/client IP until
        they are updated. This intentionally avoids consuming the ASGI request
        stream before FastAPI validates the payload.
        """
        user_id = request.headers.get(cls.USER_ID_HEADER)
        if user_id:
            return f"uid:{user_id}"

        # Use the first address when a trusted proxy supplies X-Forwarded-For.
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            ip = forwarded.split(",")[0].strip()
        else:
            ip = request.client.host if request.client else "unknown"

        return f"ip:{ip}"

    async def _check_rate(
        self, user_key: str
    ) -> tuple[bool, int, float]:
        """
        Check if the user is within rate limits using Redis counter.

        Returns:
            (allowed, remaining_requests, reset_timestamp)
        """
        now = time.time()
        window_seconds = 60
        max_requests = settings.RATE_LIMIT_PER_MINUTE

        # Use minute-bucket key for simple fixed window
        bucket = int(now // window_seconds)
        redis_key = f"chisa:ratelimit:{user_key}:{bucket}"
        reset_at = (bucket + 1) * window_seconds

        try:
            count = await redis_service.incr(redis_key)

            # Set expiry on first increment (new bucket)
            if count == 1:
                await redis_service.expire(redis_key, window_seconds + 5)

            remaining = max(0, max_requests - count)
            allowed = count <= max_requests

            return allowed, remaining, reset_at
        except Exception as e:
            # If Redis is down, allow the request (fail-open)
            log.warning("Rate limit check failed, allowing request", error=str(e))
            return True, max_requests, reset_at
