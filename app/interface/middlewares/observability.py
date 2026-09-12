"""Content-free HTTP/SSE OpenTelemetry boundary (OPS-02)."""

from __future__ import annotations

import asyncio
from time import monotonic
from typing import Any

from opentelemetry import context as otel_context
from opentelemetry.propagate import extract

from app.domain.interfaces.observability import (
    CounterSignal,
    GaugeSignal,
    HistogramSignal,
    IOperationalTelemetry,
    TelemetryDimensions,
    TraceOperation,
)


def _route_group(path_template: str | None) -> str:
    if path_template in {"/health", "/ready"}:
        return path_template
    if path_template in {"/api/v1/chat", "/api/v1/chat/stream", "/api/v1/community/chat"}:
        return path_template
    for prefix in ("auth", "chat", "community", "admin"):
        if path_template and path_template.startswith(f"/api/v1/{prefix}"):
            return f"/api/v1/{prefix}/other"
    if path_template and path_template.startswith("/assets"):
        return "/assets/*"
    if path_template and path_template.startswith("/static"):
        return "/static/*"
    return "other"


def _template(scope: dict[str, Any]) -> str | None:
    route = scope.get("route")
    value = getattr(route, "path", None)
    return value if isinstance(value, str) else None


class ObservabilityMiddleware:
    """Trace requests and streaming lifecycle without recording request content or IDs."""

    def __init__(self, app: Any, telemetry: IOperationalTelemetry) -> None:
        self.app = app
        self.telemetry = telemetry
        self._active_requests = 0
        self._active_streams = 0

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        method = str(scope.get("method", "GET")).upper()
        started = monotonic()
        response_started_at: float | None = None
        first_body_at: float | None = None
        status_code = 500
        is_stream = False
        disconnected = False
        dimensions = TelemetryDimensions(method=method)
        headers = {
            key.decode("latin-1"): value.decode("latin-1")
            for key, value in scope.get("headers", ())
            if key.lower() in {b"traceparent", b"tracestate"}
        }
        token = otel_context.attach(extract(headers))
        self._active_requests += 1
        self.telemetry.set_gauge(
            GaugeSignal.HTTP_ACTIVE_REQUESTS, self._active_requests, TelemetryDimensions()
        )

        async def receive_observed() -> dict[str, Any]:
            nonlocal disconnected
            message = await receive()
            if message.get("type") == "http.disconnect":
                disconnected = True
            return message

        async def send_observed(message: dict[str, Any]) -> None:
            nonlocal first_body_at, is_stream, response_started_at, status_code
            if message["type"] == "http.response.start":
                response_started_at = monotonic()
                status_code = int(message.get("status", 500))
                response_headers = {
                    key.lower(): value.lower() for key, value in message.get("headers", ())
                }
                is_stream = b"text/event-stream" in response_headers.get(b"content-type", b"")
                if is_stream:
                    self._active_streams += 1
                    self.telemetry.set_gauge(
                        GaugeSignal.HTTP_ACTIVE_STREAMS,
                        self._active_streams,
                        TelemetryDimensions(),
                    )
            elif message["type"] == "http.response.body" and first_body_at is None:
                first_body_at = monotonic()
            await send(message)

        try:
            with self.telemetry.span(TraceOperation.HTTP_REQUEST, dimensions) as span:
                try:
                    await self.app(scope, receive_observed, send_observed)
                except asyncio.CancelledError:
                    disconnected = True
                    span.set_status("cancelled", "client_cancelled")
                    raise
                except Exception:
                    span.set_status("error", "unhandled")
                    raise
                finally:
                    route = _route_group(_template(scope))
                    status_class = "cancelled" if disconnected else f"{status_code // 100}xx"
                    final_dimensions = TelemetryDimensions(
                        route=route,
                        method=method,
                        status_class=status_class,
                        failure_class="client_cancelled" if disconnected else None,
                    )
                    span.set_dimensions(final_dimensions)
                    if disconnected:
                        self.telemetry.count(CounterSignal.SSE_DISCONNECTS, final_dimensions)
                        self.telemetry.count(CounterSignal.HTTP_ERRORS, final_dimensions)
                    elif status_code >= 500:
                        self.telemetry.count(CounterSignal.HTTP_ERRORS, final_dimensions)
                        span.set_status("error", "unhandled")
                    else:
                        span.set_status("ok")
                    self.telemetry.count(CounterSignal.HTTP_REQUESTS, final_dimensions)
                    self.telemetry.observe(
                        HistogramSignal.HTTP_DURATION,
                        monotonic() - started,
                        final_dimensions,
                    )
                    if is_stream and first_body_at is not None:
                        self.telemetry.observe(
                            HistogramSignal.HTTP_TTFT,
                            first_body_at - started,
                            final_dimensions,
                        )
        finally:
            if is_stream:
                self._active_streams -= 1
                self.telemetry.set_gauge(
                    GaugeSignal.HTTP_ACTIVE_STREAMS,
                    self._active_streams,
                    TelemetryDimensions(),
                )
            self._active_requests -= 1
            self.telemetry.set_gauge(
                GaugeSignal.HTTP_ACTIVE_REQUESTS,
                self._active_requests,
                TelemetryDimensions(),
            )
            otel_context.detach(token)
