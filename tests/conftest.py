"""Pytest configuration and shared fixtures for Chisa test suite."""
from __future__ import annotations

import os

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

# ── Force test environment before any app imports ───────────────────
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://chisa:chisa_secret@localhost:5432/chisa_test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")  # DB 15 = isolated for tests
os.environ.setdefault("CELERY_BROKER_URL", "redis://localhost:6379/14")
os.environ.setdefault("CELERY_RESULT_BACKEND", "redis://localhost:6379/14")
os.environ.setdefault("QDRANT_URL", "http://localhost:6333")
os.environ.setdefault("GROQ_API_KEY", "test_groq_key_placeholder")
os.environ.setdefault("JWT_SECRET", "test_jwt_secret_that_is_long_enough_for_validation")
os.environ.setdefault("SECRET_KEY", "test_secret_key_that_is_long_enough_for_validation")

from app.config.settings import invalidate_settings_cache  # noqa: E402
invalidate_settings_cache()

from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


@pytest_asyncio.fixture
async def client() -> AsyncClient:
    """
    Async HTTP client for testing FastAPI routes.
    Uses ASGI transport (no real HTTP server needed).
    """
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as ac:
        yield ac
