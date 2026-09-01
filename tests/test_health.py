"""Tests for /health and /ready system endpoints."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_returns_ok(client: AsyncClient) -> None:
    """GET /health must return 200 and status='ok'."""
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "version" in data


@pytest.mark.asyncio
async def test_ready_returns_service_map(client: AsyncClient) -> None:
    """GET /ready must return a service health map (may be degraded in unit tests)."""
    response = await client.get("/ready")
    # 200 even if degraded — readiness check should not crash
    assert response.status_code in {200, 503}
    data = response.json()
    assert "status" in data
    assert "services" in data
    assert "postgresql" in data["services"]
    assert "redis" in data["services"]
    assert "qdrant" in data["services"]


@pytest.mark.asyncio
async def test_ready_returns_503_when_a_required_dependency_is_unavailable(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A degraded required dependency must keep traffic off the replica."""
    from app.interface.api.routes import health as health_route

    monkeypatch.setattr(health_route, "check_database_health", AsyncMock(return_value=True))
    monkeypatch.setattr(health_route.redis_service, "health_check", AsyncMock(return_value=True))
    monkeypatch.setattr(
        health_route.qdrant_service, "health_check", AsyncMock(return_value=False)
    )

    response = await client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "degraded",
        "services": {"postgresql": True, "redis": True, "qdrant": False},
    }
