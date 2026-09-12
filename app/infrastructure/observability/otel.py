"""Bounded, content-free OpenTelemetry adapter."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import fields
from typing import Any

from opentelemetry import metrics, trace
from opentelemetry.trace import Status, StatusCode

from app.domain.interfaces.observability import (
    CounterSignal,
    GaugeSignal,
    HistogramSignal,
    IOperationalTelemetry,
    NoopOperationalTelemetry,
    SpanHandle,
    TelemetryDimensions,
    TraceOperation,
)

_MAX_VALUES_PER_DIMENSION = 128
_ROUTES = frozenset(
    {
        "/health", "/ready", "/api/v1/chat", "/api/v1/chat/stream",
        "/api/v1/community/chat", "/api/v1/auth/other", "/api/v1/chat/other",
        "/api/v1/community/other", "/api/v1/admin/other", "/assets/*", "/static/*", "other",
    }
)
_STAGES = frozenset(
    {
        "initialization", "intent", "tool_routing", "rag", "context_building",
        "provider_pii_redaction", "llm_generation", "persistence", "emotion_update",
        "cache", "cache_update", "background_task", "hybrid", "provider_http", "grounding",
        "reranker_total",
    }
)
_MODEL_PROFILES = frozenset({"default", "flash", "reasoning", "vision"})
_PURPOSES = frozenset(
    {
        "unknown", "chat_response", "query_rewrite", "context_assessment", "thinking_loop",
        "memory_extraction", "memory_reconciliation", "private_summary", "community_summary",
        "conversation_summary",
    }
)
_CAPABILITY_PROFILES = frozenset(
    {
        "text", "structured_output+text", "streaming+text", "streaming+structured_output+text",
        "structured_output+text+tool_calling", "structured_output+text+vision",
        "streaming+structured_output+text+vision",
        "structured_output+text+tool_calling+vision",
    }
)
_JOB_TYPES = frozenset(
    {
        "memory_extraction.v1", "private_summary.v1", "community_summary.v1",
        "visual_memory.v1", "user_state_cache.v1", "private_summary_cache.v1",
        "community_state.v1",
    }
)
_ALLOWED_VALUES: dict[str, frozenset[str]] = {
    "method": frozenset({"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"}),
    "status_class": frozenset({"1xx", "2xx", "3xx", "4xx", "5xx", "cancelled"}),
    "provider": frozenset(
        {"deepseek", "gemini", "groq", "voyage", "jina", "cohere", "local", "deterministic"}
    ),
    "status": frozenset(
        {
            "ok", "error", "cancelled", "degraded", "hit", "miss", "ready", "not_ready",
            "read", "write", "succeeded", "retry_scheduled", "dead_letter", "released",
            "allow", "block", "quarantine", "verified", "abstained", "rejected",
        }
    ),
    "token_type": frozenset({"input", "output", "total"}),
    "cache_outcome": frozenset(
        {
            "hit", "miss", "bypass", "stale", "incompatible_version", "acl_mismatch",
            "malformed", "legacy_miss", "write", "write_failed", "corpus_unavailable",
            "unavailable", "identity_mismatch", "expired", "stale_version", "not_cacheable",
            "write_unavailable",
        }
    ),
    "dependency": frozenset(
        {
            "postgresql",
            "redis",
            "qdrant",
            "qdrant_index_identity",
            "llm_config",
            "llm_provider",
        }
    ),
    "failure_class": frozenset(
        {
            "none", "unhandled", "unknown", "timeout", "transport", "rate_limit",
            "provider_5xx", "auth_config", "token_overflow", "invalid_response",
            "provider_unavailable", "circuit_open", "bulkhead_rejected", "budget_exhausted",
            "deadline_exceeded", "no_compatible_provider", "client_cancelled", "output_leakage",
            "cross_tenant_denial", "grounding_failed", "dependency_unavailable",
            "queue_failure", "privacy_rejected",
        }
    ),
    "fallback_reason": frozenset(
        {
            "none", "timeout", "transport", "rate_limited", "provider_unavailable",
            "breaker_open", "circuit_open", "rate_limit", "provider_5xx",
            "invalid_response", "privacy_rejected",
        }
    ),
}


class _DimensionLimiter:
    """Guarantee bounded series count and reject content-shaped label values."""

    def __init__(self) -> None:
        self._values: dict[str, set[str]] = {}
        self._lock = threading.Lock()

    def attributes(self, dimensions: TelemetryDimensions) -> dict[str, str]:
        result: dict[str, str] = {}
        for item in fields(dimensions):
            value = getattr(dimensions, item.name)
            if value is None:
                continue
            if item.name == "route":
                normalized = value if value in _ROUTES else "other"
            elif item.name == "stage":
                normalized = value if value in _STAGES else "other"
            elif item.name == "model_profile":
                normalized = value if value in _MODEL_PROFILES else "other"
            elif item.name == "purpose":
                normalized = value if value in _PURPOSES else "other"
            elif item.name == "capability_profile":
                normalized = value if value in _CAPABILITY_PROFILES else "other"
            elif item.name == "job_type":
                normalized = value if value in _JOB_TYPES else "other"
            else:
                allowed = _ALLOWED_VALUES.get(item.name, frozenset())
                normalized = value if value in allowed else "other"
            with self._lock:
                known = self._values.setdefault(item.name, set())
                if normalized not in known and len(known) >= _MAX_VALUES_PER_DIMENSION:
                    normalized = "other"
                known.add(normalized)
            result[f"chisa.{item.name}"] = normalized
        return result



class _OtelSpanHandle:
    def __init__(self, span: trace.Span, limiter: _DimensionLimiter) -> None:
        self._span = span
        self._limiter = limiter
        self._status_set = False

    def set_dimensions(self, dimensions: TelemetryDimensions) -> None:
        for key, value in self._limiter.attributes(dimensions).items():
            self._span.set_attribute(key, value)

    def set_status(self, status: str, failure_class: str | None = None) -> None:
        self._status_set = True
        safe_status = status if status in {"ok", "error", "cancelled", "degraded"} else "error"
        self._span.set_attribute("chisa.status", safe_status)
        if failure_class is not None:
            attrs = self._limiter.attributes(
                TelemetryDimensions(failure_class=failure_class)
            )
            for key, value in attrs.items():
                self._span.set_attribute(key, value)
        if safe_status in {"error", "cancelled"}:
            self._span.set_status(Status(StatusCode.ERROR))
        else:
            self._span.set_status(Status(StatusCode.OK))


class OpenTelemetryOperationalTelemetry(IOperationalTelemetry):
    """Maps a fixed signal taxonomy to OTel instruments with bounded labels."""

    def __init__(self, tracer: trace.Tracer, meter: metrics.Meter) -> None:
        self._tracer = tracer
        self._limiter = _DimensionLimiter()
        self._counters = {
            signal: meter.create_counter(signal.value, unit="{event}") for signal in CounterSignal
        }
        self._histograms = {
            signal: meter.create_histogram(
                signal.value,
                unit="1" if signal is HistogramSignal.RAG_RETRIEVAL_SCORE else "s",
            )
            for signal in HistogramSignal
        }
        self._gauges = {
            signal: meter.create_up_down_counter(
                signal.value,
                unit="s" if signal is GaugeSignal.WORKER_QUEUE_OLDEST_READY_AGE else "{value}",
            )
            for signal in GaugeSignal
        }
        self._gauge_values: dict[tuple[GaugeSignal, tuple[tuple[str, str], ...]], float] = {}
        self._gauge_lock = threading.Lock()

    @contextmanager
    def span(
        self, operation: TraceOperation, dimensions: TelemetryDimensions
    ) -> Iterator[SpanHandle]:
        attributes = self._limiter.attributes(dimensions)
        with self._tracer.start_as_current_span(
            operation.value,
            attributes=attributes,
            record_exception=False,
            set_status_on_exception=False,
        ) as current_span:
            handle = _OtelSpanHandle(current_span, self._limiter)
            try:
                yield handle
            except BaseException:
                if not handle._status_set:
                    handle.set_status("error", "unhandled")
                raise

    def count(
        self,
        signal: CounterSignal,
        dimensions: TelemetryDimensions,
        amount: int = 1,
    ) -> None:
        if amount < 0:
            return
        self._counters[signal].add(amount, self._limiter.attributes(dimensions))

    def observe(
        self,
        signal: HistogramSignal,
        value_seconds: float,
        dimensions: TelemetryDimensions,
    ) -> None:
        if value_seconds < 0:
            return
        self._histograms[signal].record(value_seconds, self._limiter.attributes(dimensions))

    def set_gauge(
        self,
        signal: GaugeSignal,
        value: int | float,
        dimensions: TelemetryDimensions,
    ) -> None:
        attributes = self._limiter.attributes(dimensions)
        key = (signal, tuple(sorted(attributes.items())))
        with self._gauge_lock:
            previous = self._gauge_values.get(key, 0.0)
            current = float(value)
            self._gauge_values[key] = current
        self._gauges[signal].add(current - previous, attributes)


class DelegatingOperationalTelemetry(IOperationalTelemetry):
    """Stable injected reference whose backend is swapped once during startup."""

    def __init__(self, target: IOperationalTelemetry) -> None:
        self._target = target
        self._lock = threading.Lock()

    def replace(self, target: IOperationalTelemetry) -> None:
        with self._lock:
            self._target = target

    @contextmanager
    def span(
        self, operation: TraceOperation, dimensions: TelemetryDimensions
    ) -> Iterator[SpanHandle]:
        try:
            span_context = self._target.span(operation, dimensions)
            handle = span_context.__enter__()
        except Exception:
            with NoopOperationalTelemetry().span(operation, dimensions) as noop:
                yield noop
            return
        try:
            yield handle
        except BaseException as application_error:
            self._close_span(span_context, application_error)
            raise
        else:
            self._close_span(span_context, None)

    @staticmethod
    def _close_span(span_context: Any, error: BaseException | None) -> None:
        try:
            if error is None:
                span_context.__exit__(None, None, None)
            else:
                span_context.__exit__(type(error), error, error.__traceback__)
        except Exception:
            return None

    def count(
        self,
        signal: CounterSignal,
        dimensions: TelemetryDimensions,
        amount: int = 1,
    ) -> None:
        try:
            self._target.count(signal, dimensions, amount)
        except Exception:
            return None

    def observe(
        self,
        signal: HistogramSignal,
        value_seconds: float,
        dimensions: TelemetryDimensions,
    ) -> None:
        try:
            self._target.observe(signal, value_seconds, dimensions)
        except Exception:
            return None

    def set_gauge(
        self,
        signal: GaugeSignal,
        value: int | float,
        dimensions: TelemetryDimensions,
    ) -> None:
        try:
            self._target.set_gauge(signal, value, dimensions)
        except Exception:
            return None
