# Kuchiba Chisa observability assets

These files are optional, backend-facing OPS-02 deployment artifacts. The application emits
OpenTelemetry signals and does not depend on Grafana or Prometheus at runtime.

- `slo.yaml` uses the OpenSLO `openslo/v1` shape and maps each objective to an approved SRS ID.
- `alerts.yaml` uses the Prometheus Operator `PrometheusRule` shape. Availability and latency
  burn alerts use standard fast (5m/1h at 14.4x) and slow (30m/6h at 6x) windows.
- `dashboards/` contains three small Grafana-compatible dashboards. Import them only when the
  selected telemetry backend exposes Prometheus-compatible queries.

OpenTelemetry metric names use dots. Prometheus-compatible exporters normalize dots to
underscores, append `_total` to counters and append `_seconds` to instruments whose unit is
seconds. These assets query those normalized names and therefore require a collector/exporter
translation strategy equivalent to `UnderscoreEscapingWithSuffixes`. If a backend is configured
without metric suffixes, adapt the backend query layer rather than changing application metrics.

## Alert intent

- Availability and grounded-RAG burn rules page only when both windows in a pair breach the
  approved monthly error budget.
- Text response latency alerts use the approved p95 objective (8 seconds). They do not redefine
  the independent p99 or TTFT objectives shown on dashboards.
- Provider fallback, queue backlog/lag, dependency, DLQ, leakage, cross-tenant denial, index
  drift and call-budget alerts are operational symptoms. They do not create new SLOs.
- Queue alerts require a continuously non-empty and growing condition, avoiding a fixed queue
  threshold that is not present in the SRS.

Cost is deliberately not estimated here. No authoritative provider price registry exists in the
application. `ChisaLlmCostBudgetAnomaly` alerts on the approved hard per-request call-budget
exhaustion signal and token usage remains observable; a monetary-cost alert must wait for a
versioned pricing source and explicit budget approval.

## Explicit measurement boundaries

The active OpenSLO objects represent approved requirements that current OPS-02 instruments can
measure without changing their semantics. The following approved requirements stay visible as
verification/load-test obligations rather than being replaced by a misleading time series:

- `NFR-PERF-001`: end-to-end HTTP duration includes RAG/LLM time and is not the isolated
  admission/auth phase required by this objective.
- `NFR-PERF-004`: the HTTP timer does not have a safe bounded vision/text classification at the
  middleware boundary, so it cannot prove vision total-response p95.
- `NFR-PERF-005` and the sparse half of `NFR-PERF-006`: current production retrieval exposes one
  `hybrid` boundary. It does not time dense and sparse provider calls separately, so separate
  150 ms dense and 120 ms sparse SLOs cannot be inferred from that aggregate.
- `NFR-PERF-007`: concurrent-stream and resource-envelope acceptance requires the OPS-04 load
  profile. Active stream gauges alone do not prove capacity.
- `NFR-PERF-008`: ingestion throughput belongs to the canonical ingestion/load verification and
  is not inferred from worker job rate.
- `NFR-PERF-009`: hard per-request retrieval/LLM-call budgets are enforced and exhaustion is
  observable, but the SRS does not define a ratio target from which to create an SLO.

The 30-day rolling window used by latency OpenSLO objects is the reporting window, not a changed
latency threshold or load condition. Formal acceptance must still satisfy every measurement
condition stated by the mapped SRS requirement.

## Cardinality and privacy

OpenTelemetry attributes use the `chisa.*` namespace and become `chisa_*` Prometheus labels.
Queries use only bounded operational labels: `chisa_route`, `chisa_method`,
`chisa_status_class`, `chisa_stage`, `chisa_provider`, `chisa_model_profile`, `chisa_purpose`,
`chisa_capability_profile`, `chisa_cache_outcome`, `chisa_fallback_reason`,
`chisa_failure_class`, `chisa_job_type`, `chisa_dependency`, `chisa_status`, and
`chisa_token_type`.
Never add a principal, tenant, guild, channel, conversation, request, trace, cache key, query,
prompt, exception message, URL, path, or arbitrary text as a time-series label.
