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
    assert response.status_code in {200, 503}
    data = response.json()
    assert "status" in data
    assert "services" in data
    assert "postgresql" in data["services"]
    assert "redis" in data["services"]
    assert "qdrant" in data["services"]
    assert "llm_config" in data["services"]


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
        "services": {
            "postgresql": True,
            "redis": True,
            "qdrant": False,
            "llm_config": True,
        },
    }


@pytest.mark.asyncio
async def test_ready_returns_503_for_invalid_llm_configuration(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.interface.api.routes import health as health_route

    monkeypatch.setattr(health_route, "check_database_health", AsyncMock(return_value=True))
    monkeypatch.setattr(health_route.redis_service, "health_check", AsyncMock(return_value=True))
    monkeypatch.setattr(
        health_route.qdrant_service, "health_check", AsyncMock(return_value=True)
    )
    monkeypatch.setattr(
        health_route,
        "validate_llm_configuration",
        lambda _settings: ["primary LLM provider is not enabled"],
    )

    response = await client.get("/ready")

    assert response.status_code == 503
    assert response.json()["services"]["llm_config"] is False


@pytest.mark.asyncio
async def test_production_startup_fails_after_aggregating_llm_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app import main as main_module

    monkeypatch.setattr(main_module.settings, "APP_ENV", "production")
    monkeypatch.setattr(main_module, "connect_database", AsyncMock(return_value=None))
    monkeypatch.setattr(
        main_module.redis_service, "health_check", AsyncMock(return_value=False)
    )
    monkeypatch.setattr(
        main_module.qdrant_service, "health_check", AsyncMock(return_value=False)
    )
    monkeypatch.setattr(
        main_module,
        "validate_llm_configuration",
        lambda _settings: ["primary LLM provider is not enabled"],
    )

    with pytest.raises(RuntimeError, match="LLM configuration: primary LLM provider"):
        async with main_module.lifespan(main_module.app):
            pytest.fail("invalid production configuration must not reach ready state")
