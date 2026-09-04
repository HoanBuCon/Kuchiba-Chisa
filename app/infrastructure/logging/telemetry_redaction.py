"""Metadata-only redaction for operational telemetry (SEC-03, SEC-DATA-008)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

# Trace data is observable operational data, not a content store.  New fields
# must be explicitly added here after review; unknown fields are dropped.
_SAFE_TEXT_FIELDS = frozenset(
    {
        "category",
        "error_code",
        "error_type",
        "event_type",
        "finish_reason",
        "id",
        "model",
        "name",
        "pipeline",
        "provider",
        "purpose",
        "purpose_label",
        "request_id",
        "source",
        "stage_id",
        "status",
        "token_source",
    }
)
_SAFE_BOOLEAN_PREFIXES = ("has_", "is_", "use_", "needs_")
_SAFE_NUMERIC_SUFFIXES = (
    "_bytes",
    "_count",
    "_index",
    "_latency_ms",
    "_ms",
    "_score",
    "_tokens",
)
_SAFE_NUMERIC_FIELDS = frozenset(
    {
        "call_index",
        "confidence",
        "depth",
        "effective_ceiling",
        "latency_ms",
        "question_idx",
        "temperature",
        "total_estimated_tokens",
        "turn_idx",
    }
)
_SAFE_BOOLEAN_FIELDS = frozenset(
    {
        "loop_thinking_activated",
        "rag_triggered",
        "state_cache_hit",
        "within_budget",
    }
)
_SAFE_METRIC_MAPPING_FIELDS = frozenset(
    {"budget_audit", "metrics", "retrieval_metadata", "token_breakdown", "tokens"}
)


def redact_telemetry_payload(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    """Return only approved, content-free telemetry fields.

    The function deliberately drops unknown keys. This prevents a future
    pipeline stage from publishing prompt, evidence, PII, model output, or
    reasoning merely by choosing a new key name.
    """
    if not payload:
        return {}

    redacted: dict[str, Any] = {}
    for raw_key, value in payload.items():
        if not isinstance(raw_key, str):
            continue
        key = raw_key.lower()

        if key in _SAFE_TEXT_FIELDS and isinstance(value, str):
            redacted[raw_key] = value[:128]
        elif key in _SAFE_NUMERIC_FIELDS and _is_number(value):
            redacted[raw_key] = value
        elif key.endswith(_SAFE_NUMERIC_SUFFIXES) and _is_number(value):
            redacted[raw_key] = value
        elif key.startswith(_SAFE_BOOLEAN_PREFIXES) and isinstance(value, bool):
            redacted[raw_key] = value
        elif key in _SAFE_BOOLEAN_FIELDS and isinstance(value, bool):
            redacted[raw_key] = value
        elif key in _SAFE_METRIC_MAPPING_FIELDS and isinstance(value, Mapping):
            redacted[raw_key] = _redact_metric_mapping(value)

    return redacted


def _redact_metric_mapping(value: Mapping[Any, Any]) -> dict[str, int | float | bool]:
    """Metric maps may contain only scalar numbers or booleans."""
    return {
        str(key): item
        for key, item in value.items()
        if _is_number(item) or isinstance(item, bool)
    }


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)
