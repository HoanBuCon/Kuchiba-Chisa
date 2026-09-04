from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.infrastructure.cache.redis.redis_service import redis_service
from app.infrastructure.database.engine import check_database_health
from app.infrastructure.vector.qdrant.qdrant_service import qdrant_service

router = APIRouter()


# ─── Response Schemas ─────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str
    version: str = "0.1.0"


class ReadinessResponse(BaseModel):
    status: str
    services: dict[str, bool]


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Liveness probe",
    description="Returns 200 if the application process is running.",
)
async def health() -> HealthResponse:
    """
    Liveness check — used by load balancers and container orchestrators.
    Does NOT check infrastructure connectivity.
    """
    return HealthResponse(status="ok")


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    summary="Readiness probe",
    description="Returns 200 only when all backend services are reachable.",
)
async def ready() -> ReadinessResponse | JSONResponse:
    """
    Readiness check — used by Kubernetes to gate traffic.
    Checks PostgreSQL, Redis, and Qdrant connectivity.
    """
    db_ok = await check_database_health()
    redis_ok = await redis_service.health_check()
    qdrant_ok = await qdrant_service.health_check(require_active_collections=True)

    services = {
        "postgresql": db_ok,
        "redis": redis_ok,
        "qdrant": qdrant_ok,
    }

    all_ready = all(services.values())

    response = ReadinessResponse(
        status="ready" if all_ready else "degraded",
        services=services,
    )
    if not all_ready:
        return JSONResponse(status_code=503, content=response.model_dump())
    return response
