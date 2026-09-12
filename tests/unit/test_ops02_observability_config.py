"""OPS-02 typed OpenTelemetry configuration regressions."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config.settings import Settings


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


def test_observability_is_opt_in_and_uses_bounded_defaults() -> None:
    configured = _settings()

    assert configured.OTEL_ENABLED is False
    assert pytest.approx(0.05) == configured.OTEL_TRACE_SAMPLE_RATIO
    assert configured.OTEL_BSP_MAX_QUEUE_SIZE >= configured.OTEL_BSP_MAX_EXPORT_BATCH_SIZE
    assert configured.OTEL_EXPORT_TIMEOUT_SECONDS <= 30.0


@pytest.mark.parametrize("ratio", [-0.01, 1.01])
def test_trace_sampling_ratio_rejects_out_of_range_values(ratio: float) -> None:
    with pytest.raises(ValidationError, match="OTEL_TRACE_SAMPLE_RATIO"):
        _settings(OTEL_TRACE_SAMPLE_RATIO=ratio)


def test_batch_export_size_cannot_exceed_bounded_queue() -> None:
    with pytest.raises(
        ValidationError,
        match="OTEL_BSP_MAX_EXPORT_BATCH_SIZE cannot exceed OTEL_BSP_MAX_QUEUE_SIZE",
    ):
        _settings(OTEL_BSP_MAX_QUEUE_SIZE=64, OTEL_BSP_MAX_EXPORT_BATCH_SIZE=65)


def test_enabled_production_export_requires_an_otlp_endpoint() -> None:
    with pytest.raises(ValidationError, match="OTEL_EXPORTER_OTLP_ENDPOINT is required"):
        _settings(
            APP_ENV="production",
            REDIS_PASSWORD="redis-secret",
            QDRANT_API_KEY="qdrant-secret",
            OTEL_ENABLED=True,
        )


def test_otlp_headers_remain_secret_in_settings_representation() -> None:
    configured = _settings(OTEL_EXPORTER_OTLP_HEADERS="Authorization=secret-canary")

    assert "secret-canary" not in repr(configured)
    assert configured.OTEL_EXPORTER_OTLP_HEADERS is not None
    assert configured.OTEL_EXPORTER_OTLP_HEADERS.get_secret_value() == (
        "Authorization=secret-canary"
    )


def test_env_example_documents_all_operational_telemetry_controls() -> None:
    env_example = (Path(__file__).parents[2] / ".env.example").read_text(encoding="utf-8")

    for setting_name in (
        "OTEL_ENABLED",
        "OTEL_SERVICE_NAME",
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        "OTEL_EXPORTER_OTLP_HEADERS",
        "OTEL_TRACE_SAMPLE_RATIO",
        "OTEL_METRIC_EXPORT_INTERVAL_SECONDS",
        "OTEL_EXPORT_TIMEOUT_SECONDS",
        "OTEL_BSP_MAX_QUEUE_SIZE",
        "OTEL_BSP_MAX_EXPORT_BATCH_SIZE",
        "OTEL_BSP_SCHEDULE_DELAY_MS",
        "OTEL_WORKER_QUEUE_SNAPSHOT_INTERVAL_SECONDS",
    ):
        assert f"{setting_name}=" in env_example
