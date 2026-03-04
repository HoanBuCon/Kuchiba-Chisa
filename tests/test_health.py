"""Tests for /health and /ready system endpoints."""
from __future__ import annotations

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
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "services" in data
    assert "postgresql" in data["services"]
    assert "redis" in data["services"]
    assert "qdrant" in data["services"]
