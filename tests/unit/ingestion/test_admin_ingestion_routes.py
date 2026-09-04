"""HTTP regressions for admin ingestion authentication and trusted ownership."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from jose import jwt

from app.application.ingestion.source_governance import IngestionSourceGovernanceService
from app.config.settings import settings
from app.domain.models.ingestion_source import IngestionSource, IngestionSourceAuditEvent
from app.interface.api.routes.admin_ingestion import (
    get_source_governance_service,
    router,
)


class SourceRepository:
    def __init__(self) -> None:
        self.sources: dict[object, IngestionSource] = {}

    async def get_source(self, source_id: object) -> IngestionSource | None:
        return self.sources.get(source_id)

    async def save_source(self, source: IngestionSource) -> None:
        self.sources[source.source_id] = source


class AuditRepository:
    async def record(self, event: IngestionSourceAuditEvent) -> None:
        del event


def _token(scopes: list[str]) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "sub": "curator-a",
            "scopes": scopes,
            "token_use": "web",
            "source": "web",
            "tenant_id": "tenant-a",
            "iss": settings.JWT_ISSUER,
            "aud": settings.JWT_AUDIENCE,
            "iat": now,
            "exp": now + timedelta(minutes=5),
        },
        settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
    )


def _app() -> FastAPI:
    api = FastAPI()
    api.include_router(router, prefix="/api/v1")
    service = IngestionSourceGovernanceService(SourceRepository(), AuditRepository())
    api.dependency_overrides[get_source_governance_service] = lambda: service
    return api


def _registration_payload() -> dict[str, object]:
    return {
        "uri": "https://wutheringwaves.fandom.com/api.php",
        "license_identifier": "Fandom-terms-reviewed",
        "access": {"scope": "tenant", "tenant_id": "tenant-a"},
        "trust_tier": "reviewed",
        "checksum": "d" * 64,
        "crawl_schedule": "0 3 * * *",
    }


@pytest.mark.asyncio
async def test_admin_ingestion_requires_verified_credentials_and_curator_scope() -> None:
    api = _app()
    async with AsyncClient(transport=ASGITransport(app=api), base_url="http://test") as client:
        missing = await client.post("/api/v1/admin/ingestion/sources", json=_registration_payload())
        invalid = await client.post(
            "/api/v1/admin/ingestion/sources",
            headers={"Authorization": "Bearer forged.token.value"},
            json=_registration_payload(),
        )
        no_scope = await client.post(
            "/api/v1/admin/ingestion/sources",
            headers={"Authorization": f"Bearer {_token(['chat:write'])}"},
            json=_registration_payload(),
        )

    assert missing.status_code == 401
    assert invalid.status_code == 401
    assert no_scope.status_code == 403


@pytest.mark.asyncio
async def test_admin_ingestion_derives_owner_from_verified_token_not_request_fields() -> None:
    api = _app()
    payload = _registration_payload()
    payload["owner_id"] = "attacker-controlled-owner"
    async with AsyncClient(transport=ASGITransport(app=api), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/admin/ingestion/sources",
            headers={"Authorization": f"Bearer {_token(['ingestion:source:write'])}"},
            json=payload,
        )

    assert response.status_code == 422
    payload.pop("owner_id")
    async with AsyncClient(transport=ASGITransport(app=api), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/admin/ingestion/sources",
            headers={"Authorization": f"Bearer {_token(['ingestion:source:write'])}"},
            json=payload,
        )

    assert response.status_code == 201
    assert response.json()["owner_id"] == "curator-a"


@pytest.mark.asyncio
async def test_admin_ingestion_rejects_cross_tenant_registration_even_with_valid_token() -> None:
    api = _app()
    payload = _registration_payload()
    payload["access"] = {"scope": "tenant", "tenant_id": "tenant-b"}
    async with AsyncClient(transport=ASGITransport(app=api), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/admin/ingestion/sources",
            headers={"Authorization": f"Bearer {_token(['ingestion:source:write'])}"},
            json=payload,
        )

    assert response.status_code == 403
