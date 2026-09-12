"""OPS-02 privacy, cardinality, and exporter-failure regressions."""

from __future__ import annotations

import asyncio
import threading
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    SimpleSpanProcessor,
    SpanExporter,
    SpanExportResult,
)
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app.config.settings import Settings
from app.domain.interfaces.observability import (
    CounterSignal,
    GaugeSignal,
    HistogramSignal,
    TelemetryDimensions,
    TraceOperation,
)
from app.infrastructure.observability.otel import (
    DelegatingOperationalTelemetry,
    OpenTelemetryOperationalTelemetry,
)
from app.interface.middlewares.observability import ObservabilityMiddleware, _route_group


def _telemetry() -> tuple[
    OpenTelemetryOperationalTelemetry,
    InMemorySpanExporter,
    InMemoryMetricReader,
]:
    span_exporter = InMemorySpanExporter()
    tracer_provider = TracerProvider()
    tracer_provider.add_span_processor(SimpleSpanProcessor(span_exporter))
    metric_reader = InMemoryMetricReader()
    meter_provider = MeterProvider(metric_readers=(metric_reader,))
    return (
        OpenTelemetryOperationalTelemetry(
            tracer_provider.get_tracer("ops02-test"),
            meter_provider.get_meter("ops02-test"),
        ),
        span_exporter,
        metric_reader,
    )


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "APP_ENV": "test",
        "SECRET_KEY": "s" * 32,
        "DATABASE_URL": "postgresql+asyncpg://chisa:test@localhost/chisa_test",
        "JWT_SECRET": "j" * 32,
        "DISCORD_WORKLOAD_JWT_SECRET": "w" * 32,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_untrusted_dimension_values_are_collapsed_without_content_leakage() -> None:
    telemetry, exporter, metric_reader = _telemetry()
    canaries = (
        "tenant-secret-42",
        "private-user-123",
        "raw-model-customer-a",
    )

    with telemetry.span(
        TraceOperation.HTTP_REQUEST,
        TelemetryDimensions(
            route=f"/api/v1/chat/{canaries[1]}",
            stage=canaries[0],
            model_profile=canaries[2],
        ),
    ) as span:
        span.set_status("ok")
    telemetry.count(
        CounterSignal.HTTP_REQUESTS,
        TelemetryDimensions(purpose=canaries[0], job_type=canaries[1]),
    )

    exported = str(exporter.get_finished_spans())
    assert all(canary not in exported for canary in canaries)
    attributes = exporter.get_finished_spans()[0].attributes
    assert attributes["chisa.route"] == "other"
    assert attributes["chisa.stage"] == "other"
    assert attributes["chisa.model_profile"] == "other"
    metrics_data = metric_reader.get_metrics_data()
    assert metrics_data is not None
    exported_metrics = str(metrics_data)
    assert all(canary not in exported_metrics for canary in canaries)


def test_dimension_cardinality_includes_other_bucket_inside_hard_limit() -> None:
    telemetry, exporter, _metric_reader = _telemetry()

    for index in range(140):
        with telemetry.span(
            TraceOperation.PIPELINE_STAGE,
            TelemetryDimensions(stage=f"stage-{index}"),
        ):
            pass

    stage_values = {
        span.attributes["chisa.stage"] for span in exporter.get_finished_spans()
    }
    assert "other" in stage_values
    assert len(stage_values) <= 128


def test_http_route_group_never_exports_concrete_object_identifiers() -> None:
    private_identifier = "private-user-123"

    grouped = _route_group(f"/api/v1/chat/history/{private_identifier}")

    assert grouped == "/api/v1/chat/other"
    assert private_identifier not in grouped


async def _unused_receive() -> dict[str, object]:
    return {"type": "http.request", "body": b"", "more_body": False}


async def _unused_send(_message: dict[str, object]) -> None:
    return None


@pytest.mark.asyncio
async def test_request_span_uses_bounded_route_template_not_raw_path() -> None:
    telemetry, exporter, _metric_reader = _telemetry()
    private_identifier = "private-user-123"

    async def endpoint(scope, _receive, send) -> None:
        scope["route"] = SimpleNamespace(path="/api/v1/chat/history/{user_id}")
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    middleware = ObservabilityMiddleware(endpoint, telemetry)
    await middleware(
        {
            "type": "http",
            "method": "GET",
            "path": f"/api/v1/chat/history/{private_identifier}",
            "headers": [],
        },
        _unused_receive,
        _unused_send,
    )

    span = exporter.get_finished_spans()[0]
    assert span.attributes["chisa.route"] == "/api/v1/chat/other"
    assert private_identifier not in str(span.attributes)
    assert span.attributes["chisa.status"] == "ok"


@pytest.mark.asyncio
async def test_cancelled_request_is_never_recorded_as_success() -> None:
    telemetry, exporter, metric_reader = _telemetry()

    async def cancelled(scope, _receive, _send) -> None:
        scope["route"] = SimpleNamespace(path="/api/v1/chat/stream")
        raise asyncio.CancelledError

    middleware = ObservabilityMiddleware(cancelled, telemetry)
    with pytest.raises(asyncio.CancelledError):
        await middleware(
            {
                "type": "http",
                "method": "POST",
                "path": "/api/v1/chat/stream",
                "headers": [],
            },
            _unused_receive,
            _unused_send,
        )

    span = exporter.get_finished_spans()[0]
    assert span.attributes["chisa.status"] == "cancelled"
    assert span.attributes["chisa.status_class"] == "cancelled"
    metrics_data = metric_reader.get_metrics_data()
    assert metrics_data is not None
    request_metric = next(
        metric
        for resource in metrics_data.resource_metrics
        for scope in resource.scope_metrics
        for metric in scope.metrics
        if metric.name == CounterSignal.HTTP_REQUESTS.value
    )
    points = request_metric.data.data_points
    assert any(point.attributes["chisa.status_class"] == "cancelled" for point in points)
    assert all(point.attributes["chisa.status_class"] != "2xx" for point in points)


def test_initialization_failure_is_nonfatal_and_redacts_exporter_secrets(
    monkeypatch,
) -> None:
    from app.infrastructure.observability import runtime

    secret_canary = "otel-secret-must-not-be-logged"
    logger = Mock()

    def fail_exporter(**_kwargs: object) -> None:
        raise RuntimeError(secret_canary)

    monkeypatch.setattr(runtime, "OTLPSpanExporter", fail_exporter)
    monkeypatch.setattr(runtime, "log", logger)

    runtime.configure_observability(
        _settings(
            OTEL_ENABLED=True,
            OTEL_EXPORTER_OTLP_ENDPOINT="http://collector.test:4318",
            OTEL_EXPORTER_OTLP_HEADERS=f"Authorization={secret_canary}",
        )
    )

    logger.warning.assert_called_once()
    assert secret_canary not in repr(logger.warning.call_args)
    with runtime.operational_telemetry.span(
        TraceOperation.HTTP_REQUEST,
        TelemetryDimensions(route="/health"),
    ):
        pass
    runtime.shutdown_observability()


def test_async_export_failure_does_not_escape_the_request_path() -> None:
    attempted = threading.Event()

    class FailingExporter(SpanExporter):
        def export(self, _spans) -> SpanExportResult:
            attempted.set()
            return SpanExportResult.FAILURE

        def shutdown(self) -> None:
            return None

    provider = TracerProvider()
    provider.add_span_processor(
        BatchSpanProcessor(
            FailingExporter(),
            max_queue_size=64,
            max_export_batch_size=1,
            schedule_delay_millis=100,
            export_timeout_millis=100,
        )
    )
    telemetry = OpenTelemetryOperationalTelemetry(
        provider.get_tracer("ops02-failed-export-test"),
        MeterProvider().get_meter("ops02-failed-export-test"),
    )

    with telemetry.span(
        TraceOperation.HTTP_REQUEST,
        TelemetryDimensions(route="/health"),
    ) as span:
        span.set_status("ok")

    assert attempted.wait(timeout=1.0)
    provider.shutdown()


def test_instrumentation_failure_is_nonfatal_at_the_stable_runtime_boundary() -> None:
    class FailingTelemetry:
        def span(self, operation, dimensions):
            raise RuntimeError("telemetry unavailable")

        def count(self, signal, dimensions, amount=1) -> None:
            raise RuntimeError("telemetry unavailable")

        def observe(self, signal, value_seconds, dimensions) -> None:
            raise RuntimeError("telemetry unavailable")

        def set_gauge(self, signal, value, dimensions) -> None:
            raise RuntimeError("telemetry unavailable")

    telemetry = DelegatingOperationalTelemetry(FailingTelemetry())
    dimensions = TelemetryDimensions(route="/health")

    with telemetry.span(TraceOperation.HTTP_REQUEST, dimensions) as span:
        span.set_status("ok")
    telemetry.count(CounterSignal.HTTP_REQUESTS, dimensions)
    telemetry.observe(HistogramSignal.HTTP_DURATION, 0.01, dimensions)
    telemetry.set_gauge(GaugeSignal.HTTP_ACTIVE_REQUESTS, 0, dimensions)
