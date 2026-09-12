from __future__ import annotations

import time
from collections.abc import Awaitable, Callable

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.config.settings import settings
from app.domain.interfaces.observability import (
    CounterSignal,
    GaugeSignal,
    HistogramSignal,
    TelemetryDimensions,
    TraceOperation,
)
from app.infrastructure.cache.redis.redis_service import redis_service
from app.infrastructure.database.engine import check_database_health
from app.infrastructure.llm.gateway_factory import validate_llm_configuration
from app.infrastructure.observability import operational_telemetry
from app.infrastructure.vector.qdrant.qdrant_service import qdrant_service

router = APIRouter()


async def _observe_dependency(
    dependency: str,
    check: Callable[[], Awaitable[bool]],
) -> bool:
    """Run one readiness check and emit only bounded availability metadata."""
    started = time.perf_counter()
    dimensions = TelemetryDimensions(dependency=dependency)
    with operational_telemetry.span(TraceOperation.DEPENDENCY_CHECK, dimensions) as span:
        try:
            available = await check()
        except Exception:
            available = False
        status = "ready" if available else "not_ready"
        result_dimensions = TelemetryDimensions(dependency=dependency, status=status)
        span.set_dimensions(result_dimensions)
        if available:
            span.set_status("ok")
        else:
            span.set_status("degraded", "dependency_unavailable")
    operational_telemetry.count(CounterSignal.DEPENDENCY_CHECKS, result_dimensions)
    operational_telemetry.observe(
        HistogramSignal.DEPENDENCY_DURATION,
        time.perf_counter() - started,
        result_dimensions,
    )
    operational_telemetry.set_gauge(
        GaugeSignal.DEPENDENCY_AVAILABLE,
        int(available),
        TelemetryDimensions(dependency=dependency),
    )
    return available


async def _llm_configuration_ready() -> bool:
    return not validate_llm_configuration(settings)


async def _qdrant_index_identity_ready() -> bool:
    readiness = await qdrant_service.validate_active_collections()
    return all(result.ready for result in readiness.values())


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
    db_ok = await _observe_dependency("postgresql", check_database_health)
    redis_ok = await _observe_dependency("redis", redis_service.health_check)
    qdrant_connectivity_ok = await _observe_dependency(
        "qdrant", qdrant_service.health_check
    )
    qdrant_index_identity_ok = False
    if qdrant_connectivity_ok:
        qdrant_index_identity_ok = await _observe_dependency(
            "qdrant_index_identity", _qdrant_index_identity_ready
        )
    else:
        # Connectivity failure makes identity unverifiable; publish the explicit
        # unavailable state without issuing a second network request.
        async def unavailable_identity() -> bool:
            return False

        qdrant_index_identity_ok = await _observe_dependency(
            "qdrant_index_identity", unavailable_identity
        )
    qdrant_ok = qdrant_connectivity_ok and qdrant_index_identity_ok
    llm_config_ok = await _observe_dependency("llm_config", _llm_configuration_ready)

    services = {
        "postgresql": db_ok,
        "redis": redis_ok,
        "qdrant": qdrant_ok,
        "llm_config": llm_config_ok,
    }

    all_ready = all(services.values())

    response = ReadinessResponse(
        status="ready" if all_ready else "degraded",
        services=services,
    )
    if not all_ready:
        return JSONResponse(status_code=503, content=response.model_dump())
    return response
