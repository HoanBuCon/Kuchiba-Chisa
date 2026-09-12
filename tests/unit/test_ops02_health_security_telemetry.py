"""OPS-02 dependency-health and authorization-boundary telemetry regressions."""

from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.application.security import authorization
from app.application.security.authorization import AuthorizationError, AuthorizationPolicy
from app.domain.interfaces.observability import (
    CounterSignal,
    GaugeSignal,
    HistogramSignal,
    TelemetryDimensions,
    TraceOperation,
)
from app.domain.value_objects.principal import PrincipalContext
from app.interface.api.routes import health as health_route


class _Span:
    def __init__(self) -> None:
        self.dimensions: list[TelemetryDimensions] = []
        self.statuses: list[tuple[str, str | None]] = []

    def set_dimensions(self, dimensions: TelemetryDimensions) -> None:
        self.dimensions.append(dimensions)

    def set_status(self, status: str, failure_class: str | None = None) -> None:
        self.statuses.append((status, failure_class))


class _RecordingTelemetry:
    def __init__(self) -> None:
        self.spans: list[tuple[TraceOperation, TelemetryDimensions, _Span]] = []
        self.counts: list[tuple[CounterSignal, TelemetryDimensions, int]] = []
        self.observations: list[tuple[HistogramSignal, float, TelemetryDimensions]] = []
        self.gauges: list[tuple[GaugeSignal, float, TelemetryDimensions]] = []

    @contextmanager
    def span(self, operation: TraceOperation, dimensions: TelemetryDimensions):
        span = _Span()
        self.spans.append((operation, dimensions, span))
        yield span

    def count(
        self,
        signal: CounterSignal,
        dimensions: TelemetryDimensions,
        amount: int = 1,
    ) -> None:
        self.counts.append((signal, dimensions, amount))

    def observe(
        self,
        signal: HistogramSignal,
        value_seconds: float,
        dimensions: TelemetryDimensions,
    ) -> None:
        self.observations.append((signal, value_seconds, dimensions))

    def set_gauge(
        self,
        signal: GaugeSignal,
        value: int | float,
        dimensions: TelemetryDimensions,
    ) -> None:
        self.gauges.append((signal, float(value), dimensions))


def _workload_principal(
    *, tenant_id: str | None = "tenant-a", channel_id: str | None = "channel-a"
) -> PrincipalContext:
    return PrincipalContext(
        subject_id="private-user-canary",
        tenant_id=tenant_id,
        channel_id=channel_id,
        source="discord",
        kind="workload",
        scopes=frozenset({"community:write"}),
    )


@pytest.mark.asyncio
async def test_readiness_emits_separate_bounded_dependency_and_index_identity_signals(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    telemetry = _RecordingTelemetry()
    monkeypatch.setattr(health_route, "operational_telemetry", telemetry)
    monkeypatch.setattr(health_route, "check_database_health", AsyncMock(return_value=True))
    monkeypatch.setattr(health_route.redis_service, "health_check", AsyncMock(return_value=True))
    monkeypatch.setattr(health_route.qdrant_service, "health_check", AsyncMock(return_value=True))
    monkeypatch.setattr(
        health_route.qdrant_service,
        "validate_active_collections",
        AsyncMock(return_value={"character_lore": SimpleNamespace(ready=True)}),
    )
    monkeypatch.setattr(health_route, "validate_llm_configuration", lambda _settings: [])

    response = await health_route.ready()

    assert response.status == "ready"
    assert response.services == {
        "postgresql": True,
        "redis": True,
        "qdrant": True,
        "llm_config": True,
    }
    dependencies = {dimensions.dependency for _, dimensions, _ in telemetry.spans}
    assert dependencies == {
        "postgresql",
        "redis",
        "qdrant",
        "qdrant_index_identity",
        "llm_config",
    }
    assert all(
        operation is TraceOperation.DEPENDENCY_CHECK
        for operation, _, _ in telemetry.spans
    )
    assert all(signal is CounterSignal.DEPENDENCY_CHECKS for signal, _, _ in telemetry.counts)
    assert all(
        signal is HistogramSignal.DEPENDENCY_DURATION and elapsed >= 0
        for signal, elapsed, _ in telemetry.observations
    )
    assert all(
        signal is GaugeSignal.DEPENDENCY_AVAILABLE
        for signal, _, _ in telemetry.gauges
    )
    exported = repr(
        (telemetry.spans, telemetry.counts, telemetry.observations, telemetry.gauges)
    )
    assert "private-user-canary" not in exported


@pytest.mark.asyncio
async def test_readiness_keeps_503_semantics_and_marks_unverifiable_index_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    telemetry = _RecordingTelemetry()
    index_check = AsyncMock()
    monkeypatch.setattr(health_route, "operational_telemetry", telemetry)
    monkeypatch.setattr(health_route, "check_database_health", AsyncMock(return_value=True))
    monkeypatch.setattr(health_route.redis_service, "health_check", AsyncMock(return_value=True))
    monkeypatch.setattr(health_route.qdrant_service, "health_check", AsyncMock(return_value=False))
    monkeypatch.setattr(health_route.qdrant_service, "validate_active_collections", index_check)
    monkeypatch.setattr(health_route, "validate_llm_configuration", lambda _settings: [])

    response = await health_route.ready()

    assert response.status_code == 503
    assert response.body
    index_check.assert_not_awaited()
    index_gauge = next(
        value
        for signal, value, dimensions in telemetry.gauges
        if signal is GaugeSignal.DEPENDENCY_AVAILABLE
        and dimensions.dependency == "qdrant_index_identity"
    )
    assert index_gauge == 0


def test_tenant_and_channel_denials_emit_only_central_bounded_security_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    counter = SimpleNamespace(add=Mock())
    monkeypatch.setattr(authorization, "_security_events", counter)
    principal = _workload_principal()

    with pytest.raises(AuthorizationError):
        AuthorizationPolicy.require_tenant(principal, "tenant-b")
    with pytest.raises(AuthorizationError):
        AuthorizationPolicy.require_channel(principal, "channel-b")

    assert counter.add.call_count == 2
    assert all(
        call.args == (1, {"chisa.failure_class": "cross_tenant_denial"})
        for call in counter.add.call_args_list
    )
    assert "tenant-a" not in repr(counter.add.call_args_list)
    assert "channel-a" not in repr(counter.add.call_args_list)
    assert "private-user-canary" not in repr(counter.add.call_args_list)


def test_security_telemetry_failure_never_replaces_authorization_denial(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    counter = SimpleNamespace(add=Mock(side_effect=RuntimeError("export unavailable")))
    monkeypatch.setattr(authorization, "_security_events", counter)

    with pytest.raises(AuthorizationError, match="requested tenant"):
        AuthorizationPolicy.require_tenant(_workload_principal(), "tenant-b")
