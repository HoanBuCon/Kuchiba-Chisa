"""Structural and governance validation for OPS-02 backend-neutral assets."""

from __future__ import annotations

import json
import re
from dataclasses import fields
from pathlib import Path
from typing import Any

import yaml

from app.domain.interfaces.observability import (
    CounterSignal,
    GaugeSignal,
    HistogramSignal,
    TelemetryDimensions,
)
from app.infrastructure.observability.otel import (
    _ALLOWED_VALUES,
    _CAPABILITY_PROFILES,
    _JOB_TYPES,
    _MODEL_PROFILES,
    _PURPOSES,
    _ROUTES,
    _STAGES,
)

ROOT = Path(__file__).parents[2]
OBSERVABILITY = ROOT / "deploy" / "observability"
DASHBOARDS = OBSERVABILITY / "dashboards"

FORBIDDEN_LABELS = {
    "attachment_url",
    "cache_key",
    "channel_id",
    "conversation_id",
    "error_message",
    "guild_id",
    "prompt",
    "query",
    "request_id",
    "tenant_id",
    "trace_id",
    "user_id",
}
FORBIDDEN_EXPORTED_LABELS = FORBIDDEN_LABELS | {
    f"chisa_{label}" for label in FORBIDDEN_LABELS
}
APPROVED_SLO_TARGETS = {
    "chat-admission-availability": ("NFR-REL-001", 0.999),
    "grounded-rag-availability": ("NFR-REL-001", 0.995),
    "remote-reranker-provider-p95": ("NFR-PERF-006", 0.95),
    "text-rag-total-p95": ("NFR-PERF-003", 0.95),
    "text-rag-total-p99": ("NFR-PERF-003", 0.99),
    "text-rag-ttft-p50": ("NFR-PERF-002", 0.5),
    "text-rag-ttft-p95": ("NFR-PERF-002", 0.95),
}


def _load_yaml_documents(path: Path) -> list[dict[str, Any]]:
    documents = list(yaml.safe_load_all(path.read_text(encoding="utf-8")))
    assert documents
    assert all(isinstance(document, dict) for document in documents)
    return documents


def _promql_from_assets() -> list[str]:
    expressions: list[str] = []
    alerts = _load_yaml_documents(OBSERVABILITY / "alerts.yaml")[0]
    for group in alerts["spec"]["groups"]:
        expressions.extend(str(rule["expr"]) for rule in group["rules"])

    for document in _load_yaml_documents(OBSERVABILITY / "slo.yaml"):
        if document["kind"] != "SLO":
            continue
        ratio = document["spec"]["indicator"]["spec"]["ratioMetric"]
        expressions.extend(
            str(ratio[side]["metricSource"]["spec"]["query"])
            for side in ("good", "total")
        )

    for path in sorted(DASHBOARDS.glob("*.json")):
        dashboard = json.loads(path.read_text(encoding="utf-8"))
        for panel in dashboard["panels"]:
            expressions.extend(str(target["expr"]) for target in panel["targets"])
    return expressions


def test_openslo_documents_map_exactly_to_approved_requirements() -> None:
    documents = _load_yaml_documents(OBSERVABILITY / "slo.yaml")

    assert documents[0]["apiVersion"] == "openslo/v1"
    assert documents[0]["kind"] == "Service"
    slos = {document["metadata"]["name"]: document for document in documents[1:]}
    assert set(slos) == set(APPROVED_SLO_TARGETS)

    for name, (requirement, target) in APPROVED_SLO_TARGETS.items():
        slo = slos[name]
        assert slo["apiVersion"] == "openslo/v1"
        assert slo["kind"] == "SLO"
        assert slo["metadata"]["annotations"]["srs_requirement"] == requirement
        assert slo["spec"]["timeWindow"] == [{"duration": "30d", "isRolling": True}]
        assert slo["spec"]["objectives"][0]["target"] == target
        ratio = slo["spec"]["indicator"]["spec"]["ratioMetric"]
        assert ratio["counter"] is True
        assert {"good", "total"} <= set(ratio)


def test_openslo_queries_preserve_all_srs_latency_thresholds() -> None:
    text = (OBSERVABILITY / "slo.yaml").read_text(encoding="utf-8")

    for approved_boundary in ('le="1.5"', 'le="3.5"', 'le="8.0"', 'le="15.0"'):
        assert approved_boundary in text
    assert 'le="0.75"' in text
    assert 'chisa_stage="provider_http"' in text


def test_prometheus_rule_has_multi_window_burn_pairs_and_actionable_signals() -> None:
    rule = _load_yaml_documents(OBSERVABILITY / "alerts.yaml")[0]

    assert rule["apiVersion"] == "monitoring.coreos.com/v1"
    assert rule["kind"] == "PrometheusRule"
    rules = {
        item["alert"]: item
        for group in rule["spec"]["groups"]
        for item in group["rules"]
    }
    required = {
        "ChisaChatAdmissionAvailabilityFastBurn",
        "ChisaChatAdmissionAvailabilitySlowBurn",
        "ChisaGroundedRagAvailabilityFastBurn",
        "ChisaGroundedRagAvailabilitySlowBurn",
        "ChisaTextRagLatencyFastBurn",
        "ChisaTextRagLatencySlowBurn",
        "ChisaProviderFallbackSustained",
        "ChisaWorkerQueueBacklogGrowing",
        "ChisaWorkerDlqGrowth",
        "ChisaRequiredDependencyUnavailable",
        "ChisaOutputLeakageDetected",
        "ChisaCrossTenantAccessDenied",
        "ChisaCorpusIndexDrift",
        "ChisaLlmCostBudgetAnomaly",
    }
    assert required == set(rules)

    for prefix in (
        "ChisaChatAdmissionAvailability",
        "ChisaGroundedRagAvailability",
        "ChisaTextRagLatency",
    ):
        fast = str(rules[f"{prefix}FastBurn"]["expr"])
        slow = str(rules[f"{prefix}SlowBurn"]["expr"])
        assert "[5m]" in fast and "[1h]" in fast
        assert "[30m]" in slow and "[6h]" in slow

    for item in rules.values():
        assert item["labels"]["requirement"].startswith("NFR-")
        assert item["annotations"]["summary"]
        assert item["annotations"]["intent"]


def test_three_dashboards_are_minimal_valid_and_operationally_distinct() -> None:
    paths = sorted(DASHBOARDS.glob("*.json"))

    assert [path.name for path in paths] == [
        "rag-llm.json",
        "system-api.json",
        "worker-dependencies.json",
    ]
    dashboard_uids: set[str] = set()
    for path in paths:
        dashboard = json.loads(path.read_text(encoding="utf-8"))
        assert dashboard["schemaVersion"] >= 39
        assert dashboard["uid"] not in dashboard_uids
        dashboard_uids.add(dashboard["uid"])
        assert 1 <= len(dashboard["panels"]) <= 8
        assert len({panel["id"] for panel in dashboard["panels"]}) == len(
            dashboard["panels"]
        )
        assert all(panel["targets"] for panel in dashboard["panels"])
        assert dashboard["templating"]["list"][0]["name"] == "DS_PROMETHEUS"


def test_promql_uses_only_bounded_operational_labels() -> None:
    label_pattern = re.compile(r"\{([^{}]*)\}")
    label_name_pattern = re.compile(r"([a-zA-Z_:][a-zA-Z0-9_:]*)\s*(?:=~|!~|!=|=)")

    expressions = _promql_from_assets()
    assert expressions
    for expression in expressions:
        for selector in label_pattern.findall(expression):
            labels = set(label_name_pattern.findall(selector))
            assert not labels & FORBIDDEN_EXPORTED_LABELS


def test_promql_labels_and_values_match_exported_dimension_taxonomy() -> None:
    selector_pattern = re.compile(r"\{([^{}]*)\}")
    matcher_pattern = re.compile(
        r'([a-zA-Z_:][a-zA-Z0-9_:]*)\s*(=~|!~|!=|=)\s*"([^"]*)"'
    )
    group_pattern = re.compile(r"\bby\s*\(([^)]*)\)")
    legend_pattern = re.compile(r"\{\{([^{}]+)\}\}")
    exported_labels = {
        f"chisa_{item.name}" for item in fields(TelemetryDimensions)
    }
    rule_engine_labels = {"alertname", "alertstate", "severity"}
    allowed_query_labels = exported_labels | rule_engine_labels | {"le"}
    value_taxonomy = {
        "chisa_route": _ROUTES,
        "chisa_stage": _STAGES,
        "chisa_model_profile": _MODEL_PROFILES,
        "chisa_purpose": _PURPOSES,
        "chisa_capability_profile": _CAPABILITY_PROFILES,
        "chisa_job_type": _JOB_TYPES,
        **{f"chisa_{name}": values for name, values in _ALLOWED_VALUES.items()},
    }

    expressions = _promql_from_assets()
    for expression in expressions:
        for selector in selector_pattern.findall(expression):
            for label, operator, raw_value in matcher_pattern.findall(selector):
                assert label in allowed_query_labels
                if label == "le" or label in rule_engine_labels or operator in {"!=", "!~"}:
                    continue
                values = raw_value.split("|") if operator == "=~" else [raw_value]
                assert set(values) <= value_taxonomy[label]
        for group in group_pattern.findall(expression):
            labels = {label.strip() for label in group.split(",")}
            assert labels <= allowed_query_labels

    for dashboard_path in DASHBOARDS.glob("*.json"):
        dashboard = json.loads(dashboard_path.read_text(encoding="utf-8"))
        for panel in dashboard["panels"]:
            for target in panel["targets"]:
                labels = set(legend_pattern.findall(target.get("legendFormat", "")))
                assert labels <= exported_labels | rule_engine_labels


def test_promql_metric_names_resolve_to_declared_otel_instruments() -> None:
    exported_labels = {
        f"chisa_{item.name}" for item in fields(TelemetryDimensions)
    }
    counters = {
        f"{signal.value.replace('.', '_')}_total" for signal in CounterSignal
    }
    duration_histograms = {
        f"{signal.value.replace('.', '_')}_seconds_{suffix}"
        for signal in HistogramSignal
        for suffix in ("bucket", "count", "sum")
        if signal is not HistogramSignal.RAG_RETRIEVAL_SCORE
    }
    score_histogram = {
        f"{HistogramSignal.RAG_RETRIEVAL_SCORE.value.replace('.', '_')}_{suffix}"
        for suffix in ("bucket", "count", "sum")
    }
    gauges = {
        signal.value.replace(".", "_")
        + ("_seconds" if signal is GaugeSignal.WORKER_QUEUE_OLDEST_READY_AGE else "")
        for signal in GaugeSignal
    }
    declared_series = counters | duration_histograms | score_histogram | gauges

    observed_series: set[str] = set()
    for expression in _promql_from_assets():
        observed_series.update(re.findall(r"\bchisa_[a-z0-9_]+\b", expression))
    observed_series -= exported_labels

    assert observed_series <= declared_series
    assert "chisa_security_events_total" in observed_series
    assert "chisa_rag_reranker_privacy_rejections_total" in observed_series


def test_assets_do_not_contain_sensitive_content_canaries() -> None:
    machine_assets = [
        OBSERVABILITY / "alerts.yaml",
        OBSERVABILITY / "slo.yaml",
        *sorted(DASHBOARDS.glob("*.json")),
    ]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in machine_assets)

    assert "secret-canary" not in combined
    assert "protected-persona-canary" not in combined
    assert "raw_prompt" not in combined
    assert "authorization_token" not in combined
