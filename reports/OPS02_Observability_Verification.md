# OPS-02 Observability Verification

Status: **PASS**
Verified: **2026-10-04 (Asia/Saigon)**
Traceability: `OPS-02`, `NFR-OPS-001`, `NFR-OPS-002`, `NFR-OPS-003`,
`NFR-PERF-002`, `NFR-PERF-003`, `NFR-PERF-006`, `NFR-PERF-009`,
`NFR-REL-001`, `NFR-REL-002`, `NFR-REL-006`

## 1. Audit findings and gap matrix

Before OPS-02, Kuchiba Chisa had structured logs, a local pipeline tracker, health
checks and several component-local counters, but no shared OpenTelemetry runtime,
bounded metric taxonomy, versioned SLO assets, burn alerts or operator dashboards.

| Requirement | Previous behavior | Missing evidence | Minimal resolution |
|---|---|---|---|
| End-to-end operational tracing | Pipeline tracker was local and content-bearing; provider/worker boundaries were not shared OTel spans | Correlated, backend-neutral trace tree | Added OTel spans at HTTP/interface, pipeline/stage, retrieval, rerank, LLM, grounding, worker and dependency boundaries |
| Safe operational metrics | Signals were fragmented and not exportable through one contract | API/RAG/LLM/cache/worker/dependency telemetry | Added fixed typed signal enums and one OTel adapter |
| Privacy/cardinality | No centralized metric-label allowlist | Proof that content/IDs cannot become time-series dimensions | Added immutable typed dimensions, exact allowlists, `other` collapse and a hard per-dimension ceiling |
| SLO representation | SRS thresholds existed only as prose/tables | Machine-readable SLI/target/window mappings | Added seven OpenSLO documents using only approved thresholds |
| Burn/action alerts | No versioned alert rules | Fast/slow error-budget burn and actionable component symptoms | Added three fast/slow pairs plus eight bounded symptom alerts |
| Operator views | No minimal shared dashboard set | API, RAG/LLM and worker/dependency diagnosis | Added three backend-importable dashboards |
| Export failure safety | No OTLP exporter lifecycle | Non-fatal, bounded buffering and timeouts | Added opt-in OTLP/HTTP exporters, 5% parent-based sampling, bounded BSP queue/batch and bounded shutdown |
| Cost visibility | No authoritative versioned provider pricing registry | Honest cost-control evidence | Export provider-reported tokens and hard call-budget exhaustion; do not fabricate currency cost |
| Correct streaming TTFT | First SSE body was initially observable but it is a metadata event | Actual first-token measurement | Route marks the first emitted token using an internal timestamp; middleware never parses or exports stream content |
| Isolated verification packaging | Test image omitted OPS-02 deployment assets and `.env.example` | Linux artifact validation | Test stage now copies the exact files validated by OPS-02 tests |

## 2. Telemetry architecture

Before:

```text
routes/services -> structured logs + local PipelineTracker
```

After:

```text
interface/application/domain service boundaries
    -> IOperationalTelemetry (typed, backend-neutral port)
    -> DelegatingOperationalTelemetry (non-fatal stable reference)
    -> OpenTelemetry SDK
    -> bounded OTLP/HTTP batch exporters
    -> optional operator-selected compatible backend
```

Domain and application behavior do not depend on Grafana, Prometheus, Tempo or a
managed vendor. Dashboard PromQL is confined to deployment assets. With telemetry
disabled or initialization/export failure, the stable boundary degrades to a no-op;
request, stream, worker and readiness correctness remain unchanged.

## 3. Trace boundaries

| Operation | Boundary | Safe attributes |
|---|---|---|
| `http.request` | HTTP/interface adapter and full SSE lifetime | route group, method, status class |
| `chat.pipeline` | Chat pipeline | status only |
| `chat.pipeline.stage` | Meaningful pipeline stages | fixed stage |
| `rag.retrieval` | Production hybrid retrieval | stage/dependency/status |
| `rag.rerank` | Total rerank and remote provider HTTP | provider/stage/failure class |
| `llm.generation` | Logical generation request | model profile/purpose |
| `llm.provider` | Individual BE-02 provider attempt | provider/profile/purpose/capability |
| `rag.grounding` | Typed grounding/output validation | fixed status/failure class |
| `worker.job` | BE-01 durable job execution | fixed job type/status/failure class |
| `dependency.check` | Readiness dependency probe | fixed dependency/status |

Incoming W3C `traceparent`/`tracestate` is extracted at the HTTP boundary, and normal
async execution inherits the current OTel context. Structured logs receive trace and
span IDs for correlation; those IDs are never metric labels. Durable worker execution
has an independent safe operational span. Persisted job correctness does not depend
on trace baggage, and no prompt/content/identity is stored to propagate a trace.

## 4. Metric inventory

| Area | Counters | Histograms | Gauges |
|---|---|---|---|
| HTTP/SSE | requests, errors, disconnects | server duration, first-token TTFT | active requests, active streams |
| RAG | abstentions, grounding failures/decisions, reranker calls/errors/fallbacks/privacy rejections | retrieval, reranker provider HTTP, reranker total, top-1 score, grounding | — |
| LLM/BE-02 | provider calls/errors, retries, fallbacks, breaker opens, bulkhead rejections, degraded results, budget exhaustion, provider-reported tokens | provider duration, provider TTFT where streaming exposes it, generation duration, bulkhead wait | — |
| Cache/TD-025 | hit/miss/bypass/stale/version/ACL/malformed/write outcomes through one operation counter | — | — |
| Worker/BE-01 | jobs, retries, failures, DLQ, audited replay | processing duration | active jobs, ready depth, oldest-ready age |
| Dependencies/security | dependency checks, guardrail decisions, leakage/cross-tenant events | dependency check duration | dependency availability and Qdrant index identity |

Currency cost is deliberately unavailable: the repository has no authoritative,
versioned price registry. `ChisaLlmCostBudgetAnomaly` uses the approved hard
per-request call-budget exhaustion signal as an actionable cost-control anomaly;
token counters retain provider/profile/purpose/type slices.

## 5. Cardinality and privacy review

The only custom dimension fields are:

`route`, `method`, `status_class`, `stage`, `provider`, `model_profile`, `purpose`,
`capability_profile`, `cache_outcome`, `fallback_reason`, `failure_class`, `job_type`,
`dependency`, `status`, and `token_type`.

Every value is checked against a fixed allowlist (with separately fixed route, stage,
purpose, model, capability and job taxonomies). Unknown values collapse to `other`;
the limiter also enforces at most 128 observed values per dimension. Tests prove that
untrusted route/object IDs and content-shaped values do not survive into spans or
metrics.

Explicitly absent from metric labels and telemetry payloads: principal/user/tenant/
guild/channel/conversation/request/cache identifiers, queries, raw prompts, protected
prompts, conversation text, memory, PII, authorization/API secrets, provider payloads,
chain-of-thought, exception messages and attachment URL/path values.

The SSE TTFT path shares only a monotonic timestamp in the request-local ASGI scope.
It neither parses nor exports the metadata/token body.

## 6. SLO definitions

`deploy/observability/slo.yaml` contains seven 30-day rolling OpenSLO objectives:

| SLO | SRS source | Approved target |
|---|---|---|
| Chat admission availability | `NFR-REL-001` | 99.9% |
| Grounded RAG availability | `NFR-REL-001` | 99.5% |
| Text RAG TTFT p50 | `NFR-PERF-002` | <= 1.5 s |
| Text RAG TTFT p95 | `NFR-PERF-002` | <= 3.5 s |
| Text RAG total p95 | `NFR-PERF-003` | <= 8 s |
| Text RAG total p99 | `NFR-PERF-003` | <= 15 s |
| Remote reranker provider HTTP p95 | `NFR-PERF-006` | <= 750 ms, quota pacing excluded |

The asset documents the measurements that OPS-02 cannot truthfully infer from the
current aggregate boundaries: isolated admission/auth, vision response, separate
dense/sparse latency, concurrency/resource capacity, ingestion throughput and a
currency-cost SLO. Those remain their existing load/acceptance obligations; no SRS
threshold is changed or waived.

## 7. Alert rules

`deploy/observability/alerts.yaml` contains 14 alerts:

- fast (`5m` + `1h`, 14.4x) and slow (`30m` + `6h`, 6x) burn pairs for chat
  availability, grounded-RAG availability and text-RAG latency;
- sustained LLM/reranker provider failure with fallback;
- continuously non-empty and growing queue depth/oldest-ready age;
- DLQ growth;
- required dependency unavailability;
- output leakage detection;
- cross-tenant access denial;
- Qdrant/corpus index identity drift;
- LLM hard call-budget cost-control anomaly.

The symptom alerts have dwell windows where appropriate and do not invent new SLO
thresholds. They expose only fixed labels and sanitized failure classes.

## 8. Dashboards

| Dashboard | Panels | Operator questions |
|---|---:|---|
| `system-api.json` | 8 | Health, traffic, errors, latency, active requests/streams, dependencies and active SLO burns |
| `rag-llm.json` | 8 | Retrieval/rerank/grounding latency, TTFT, scores, abstention, provider/fallback/budget/token behavior |
| `worker-dependencies.json` | 8 | Queue depth/lag, workers, retries/DLQ/replay, cache outcomes and dependency health/latency |

Assets are standards-compatible but optional. OPS-02 does not mandate or deploy a
heavy Prometheus/Grafana/Loki/Tempo stack on the target VPS.

## 9. Resource footprint and failure safety

Typed defaults are deliberately small and bounded:

- tracing is opt-in and parent-based sampled at `0.05`;
- BatchSpanProcessor queue `512`, export batch `128`, schedule delay `5 s`;
- OTLP export timeout `3 s` (validated upper bound `30 s`);
- metric export and worker queue snapshots every `30 s`;
- unknown label values collapse instead of creating new series;
- telemetry operations are best-effort through a non-fatal delegating boundary;
- no local telemetry datastore or retention-heavy backend is added.

The settings validators reject invalid sample ratios, an export batch larger than its
queue and production enablement without an endpoint. Export initialization failure,
async export failure and instrumentation failure tests prove the application path
continues. This verifies a bounded resource envelope appropriate to the 4-vCPU/6-GB
target without claiming OPS-04 load-capacity evidence.

## 10. Verification evidence

| Gate | Result |
|---|---|
| Focused OPS-02 observability, assets/config and health/security telemetry tests | **28 passed**, 1 dependency warning |
| Isolated Linux Compose: Alembic upgrade/check, full Ruff debt audit, mypy, unit + integration | **594 passed**, 2 dependency warnings |
| Mypy | **PASS**, 297 application files |
| Changed-lines Ruff against pre-OPS-02 base `f7a3b64` | **PASS** |
| Ruff debt ratchet | **PASS**, 2,816 current <= 2,914 baseline; zero blocking rules |
| `pip check` (host and isolated Linux test image) | **PASS** |
| `compileall -q app` | **PASS** |
| Compose config validation | **PASS** |
| OpenSLO/PrometheusRule/dashboard parsing and metric/label cross-check | **PASS** |
| `git diff --check` | **PASS** |
| Protected prompt diff against pre-OPS-02 base `f7a3b64` | **PASS**, no changes |

A broad host `pytest -q` run earlier produced 666 passes plus failures/errors because
the configured PostgreSQL/Redis/Qdrant ports were not an isolated test stack. The
authoritative disposable Linux run used fresh project-scoped volumes/network, no host
ports, and passed all 594 CI-scoped unit/integration tests after the final SSE TTFT
correction. Alembic upgrade and drift checks passed; the legacy full-repo Ruff audit
reported 2,816 findings, below the 2,914 baseline, while changed-lines Ruff passed.
The isolated project was removed after verification. No failure was hidden with
skip/xfail, and no active production collection or database was mutated.

## 11. Remaining limitations

- No currency-cost metric is emitted until a versioned price source is approved.
- Backend deployment/retention is intentionally operator-selected; application code
  emits standard OTLP/HTTP only.
- Durable worker spans are independently diagnosable but are not linked by persisted
  user/content baggage across restarts.
- DB pool internals and per-SQL/per-Redis-key telemetry are intentionally excluded;
  bounded readiness health/latency is exposed instead.
- Load, capacity, chaos, backup/restore and delivery/on-call exercises remain `OPS-04`.
- Automated RAG/security release evaluation remains `OPS-03`; channel contract work
  remains `CH-01`.

These limitations do not weaken `NFR-OPS-001..003` or change any approved threshold.

## 12. Closure and P2 progress

`OPS-02`: **PASS**. The final isolated run includes the updated SSE first-token
measurement and all acceptance evidence required by the task. Primary P2 backlog
progress is **5/8 (62.5%)**:

- PASS: `BE-01`, `BE-02`, `BE-03`, `DB-01`, `OPS-02`;
- OPEN: `OPS-03`, `CH-01`, `OPS-04`.

Recommended next task: **OPS-03 — Automated RAG/security evaluation CI gate**.
Do not begin it as part of OPS-02.
