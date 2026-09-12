"""Lifecycle-owned OpenTelemetry SDK/exporter configuration."""

from __future__ import annotations

from urllib.parse import urljoin

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.metrics.view import ExplicitBucketHistogramAggregation, View
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased

from app.config.settings import Settings
from app.domain.interfaces.observability import HistogramSignal, NoopOperationalTelemetry
from app.infrastructure.logging.logger import get_logger
from app.infrastructure.observability.otel import (
    DelegatingOperationalTelemetry,
    OpenTelemetryOperationalTelemetry,
)

log = get_logger(__name__)

operational_telemetry = DelegatingOperationalTelemetry(NoopOperationalTelemetry())
_tracer_provider: TracerProvider | None = None
_meter_provider: MeterProvider | None = None

_SRS_DURATION_BUCKETS = (
    0.05,
    0.1,
    0.12,
    0.15,
    0.25,
    0.5,
    0.75,
    1.0,
    1.5,
    3.5,
    5.0,
    8.0,
    15.0,
    30.0,
    60.0,
)


def _metric_views() -> tuple[View, ...]:
    return tuple(
        View(
            instrument_name=signal.value,
            aggregation=ExplicitBucketHistogramAggregation(
                boundaries=list(_SRS_DURATION_BUCKETS)
            ),
        )
        for signal in HistogramSignal
        if signal is not HistogramSignal.RAG_RETRIEVAL_SCORE
    ) + (
        View(
            instrument_name=HistogramSignal.RAG_RETRIEVAL_SCORE.value,
            aggregation=ExplicitBucketHistogramAggregation(
                boundaries=[0.0, 0.25, 0.5, 0.75, 0.9, 1.0]
            ),
        ),
    )


def _headers(settings: Settings) -> dict[str, str]:
    secret = settings.OTEL_EXPORTER_OTLP_HEADERS
    if secret is None:
        return {}
    result: dict[str, str] = {}
    for pair in secret.get_secret_value().split(","):
        key, separator, value = pair.strip().partition("=")
        if separator and key and value:
            result[key] = value
    return result


def _signal_endpoint(base: str, signal_path: str) -> str:
    normalized = base.rstrip("/") + "/"
    return urljoin(normalized, signal_path.lstrip("/"))


def configure_observability(settings: Settings) -> None:
    """Enable bounded OTLP/HTTP export; disabled telemetry stays a no-op."""
    global _meter_provider, _tracer_provider

    if not settings.OTEL_ENABLED:
        operational_telemetry.replace(NoopOperationalTelemetry())
        return
    endpoint = settings.OTEL_EXPORTER_OTLP_ENDPOINT
    if endpoint is None:
        log.warning("OpenTelemetry disabled because no OTLP endpoint is configured")
        operational_telemetry.replace(NoopOperationalTelemetry())
        return

    try:
        headers = _headers(settings)
        timeout = settings.OTEL_EXPORT_TIMEOUT_SECONDS
        resource = Resource.create(
            {
                "service.name": settings.OTEL_SERVICE_NAME,
                "deployment.environment.name": settings.APP_ENV,
            }
        )
        base = str(endpoint)
        span_exporter = OTLPSpanExporter(
            endpoint=_signal_endpoint(base, "/v1/traces"), headers=headers, timeout=timeout
        )
        _tracer_provider = TracerProvider(
            resource=resource,
            sampler=ParentBased(TraceIdRatioBased(settings.OTEL_TRACE_SAMPLE_RATIO)),
        )
        _tracer_provider.add_span_processor(
            BatchSpanProcessor(
                span_exporter,
                max_queue_size=settings.OTEL_BSP_MAX_QUEUE_SIZE,
                max_export_batch_size=settings.OTEL_BSP_MAX_EXPORT_BATCH_SIZE,
                schedule_delay_millis=settings.OTEL_BSP_SCHEDULE_DELAY_MS,
                export_timeout_millis=int(timeout * 1_000),
            )
        )
        metric_exporter = OTLPMetricExporter(
            endpoint=_signal_endpoint(base, "/v1/metrics"), headers=headers, timeout=timeout
        )
        reader = PeriodicExportingMetricReader(
            metric_exporter,
            export_interval_millis=int(settings.OTEL_METRIC_EXPORT_INTERVAL_SECONDS * 1_000),
            export_timeout_millis=int(timeout * 1_000),
        )
        _meter_provider = MeterProvider(
            resource=resource,
            metric_readers=(reader,),
            views=_metric_views(),
        )
        # AuthorizationPolicy uses the backend-neutral OpenTelemetry API directly
        # so the application security boundary does not depend on infrastructure.
        # Providers are installed once per process; exporters remain lifecycle-owned
        # and bounded by the settings above.
        trace.set_tracer_provider(_tracer_provider)
        metrics.set_meter_provider(_meter_provider)
        telemetry = OpenTelemetryOperationalTelemetry(
            _tracer_provider.get_tracer("chisa"), _meter_provider.get_meter("chisa")
        )
        operational_telemetry.replace(telemetry)
        log.info(
            "OpenTelemetry export enabled",
            service=settings.OTEL_SERVICE_NAME,
            sample_ratio=settings.OTEL_TRACE_SAMPLE_RATIO,
        )
    except Exception as error:
        operational_telemetry.replace(NoopOperationalTelemetry())
        log.warning(
            "OpenTelemetry initialization failed; continuing without export",
            failure_class=type(error).__name__,
        )


def shutdown_observability() -> None:
    """Best-effort bounded flush; exporter failure never blocks application shutdown."""
    global _meter_provider, _tracer_provider

    try:
        if _meter_provider is not None:
            _meter_provider.shutdown()
        if _tracer_provider is not None:
            _tracer_provider.shutdown()
    except Exception as error:
        log.warning(
            "OpenTelemetry shutdown failed",
            failure_class=type(error).__name__,
        )
    finally:
        _meter_provider = None
        _tracer_provider = None
        operational_telemetry.replace(NoopOperationalTelemetry())
