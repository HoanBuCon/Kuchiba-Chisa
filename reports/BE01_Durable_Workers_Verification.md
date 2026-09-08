# BE-01 — Durable asynchronous workers

Date: 2026-09-08
Branch: `reliability/p2-be01-durable-workers`
Traceability: `BE-01`, `NFR-REL-006`, `NFR-REL-008`, `NFR-OPS-002`, `TD-020`

## Pre-implementation acceptance matrix

| Requirement | Required evidence | Initial state |
|---|---|---|
| Transactional producer/outbox atomicity | Job and source state commit or roll back in the same PostgreSQL transaction | FAIL — coroutine existed only in process memory |
| Durable queue and state | Alembic-owned PostgreSQL records survive API/worker restart | FAIL |
| Atomic lease and stale-worker fencing | Concurrent claim, expiry/reclaim, stale completion tests | FAIL |
| Bounded retry/backoff and DLQ | Retry schedule, exhaustion, terminal state, controlled replay tests | FAIL |
| Idempotent side effects | Duplicate enqueue/delivery does not duplicate memory/image/summary state | FAIL |
| Separate worker and graceful shutdown | Dedicated entrypoint; stop claiming, drain/release with bounded timeout | FAIL |
| Payload privacy | Typed, versioned, size-bounded payloads without secrets/protected prompts/raw PII | FAIL |
| Alembic-only schema ownership | Migration upgrade and drift check | Pending implementation |
| Isolated verification and protected prompts unchanged | Linux Compose gates and final diff audit | Pending implementation |

## Background-side-effect audit

| Path | Side effect | Classification | BE-01 disposition |
|---|---|---|---|
| `BackgroundTaskStage` memory extraction | LLM extraction and Qdrant memory writes | Must become durable | PostgreSQL outbox job |
| `BackgroundTaskStage` private summary | LLM generation, PostgreSQL summary, Redis cache | Must become durable | PostgreSQL outbox job |
| `BackgroundTaskStage` community topic summary | LLM generation and Redis derived state | Must become durable | PostgreSQL outbox job |
| `BackgroundTaskStage` visual memory ingestion | Embedding and Qdrant image-memory upsert | Must become durable | PostgreSQL outbox job |
| SSE route runner | Owns the live response stream and is cancelled when the client disconnects | Request-local | Retain tracked in-process task |
| Dense/sparse retrieval tasks | Parallel branches are awaited before request completion | Request-local | Retain |
| entity-cache polling and Redis subscriber | Long-lived process-local coordination loops | Best-effort lifecycle | Retain with lifecycle shutdown |
| pipeline-tracker Redis publication/history | Redacted telemetry only; request correctness does not depend on delivery | Best-effort/non-durable | Retain; full telemetry belongs to OPS-02 |
| vision-storage LRU quota task | Local bounded cleanup, not creation of durable user memory | Best-effort maintenance | Retain; operational cleanup follow-up if metrics show need |
| retrieved-image attachment preparation | Request-bound rendering preparation | Request-local | Retain |

## Queue architecture decision

Selected: **PostgreSQL transactional outbox consumed directly as a durable job
queue** using `FOR UPDATE SKIP LOCKED`, expiring leases, and per-claim fencing
tokens.

This is the smallest design satisfying producer atomicity because chat messages,
stats, and outbox records share the existing SQLAlchemy transaction. A Redis/Celery
queue would still require an outbox dispatcher and a second delivery protocol to
bridge the PostgreSQL/Redis commit gap. The direct PostgreSQL design adds no new
service on the 4-vCPU/6-GB VPS, is owned by Alembic, supports crash recovery and
DLQ state, and leaves room for BE-03/OPS-02 without coupling the domain to a queue
SDK. Existing Celery settings are unused legacy configuration and are not treated
as evidence of durable delivery.

## Final verification receipt

## Before/after execution model

Before BE-01, memory extraction, private summary, community summary and visual
memory ingestion were coroutine objects registered with the process-local
`BackgroundTaskManager`. An API crash or redeploy discarded acknowledged work.

After BE-01, `PersistenceStage` captures the exact persisted user/assistant
message IDs and `BackgroundTaskStage` inserts typed jobs through the same
SQLAlchemy transaction. `app.worker` is the only executor for those job types.
It rehydrates source messages by principal-owned IDs, rechecks current consent,
claims with `FOR UPDATE SKIP LOCKED`, renews leases and fences all state changes
with a per-claim token.

## Migrated jobs and replay protection

| Job type | Persisted payload | Idempotency / replay behavior |
|---|---|---|
| `memory_extraction.v1` | Principal/conversation/message references and redacted scope metadata | Keyed by source assistant message; Qdrant IDs are UUIDv5 over the job key, fact index/type/content; durable conflict replacement upserts before deleting the superseded point |
| `private_summary.v1` | Principal and conversation references | Keyed by source assistant message; overwrites the same conversation summary and Redis derived cache key |
| `community_summary.v1` | Principal, guild/channel and trace reference | Keyed by guild/channel/rolling-buffer interval; overwrites the same Redis summary key |
| `visual_memory.v1` | Principal/conversation/message references plus redacted bounded tags/caption | Keyed by source assistant message; existing UUIDv5 image point identity is retained |

The queue payload validator rejects secret/password/API-key/system-prompt/persona
fields, strings over 8 KiB and payloads over 32 KiB. Raw chat and attachment
content remain in their governed source records and are not duplicated into the
outbox.

## Lease, retry, DLQ and operations

- Claims are atomic and exclusive; expired leases are reclaimable.
- Completion, failure, renewal and shutdown release require the active fencing
  token and an unexpired lease.
- Retry uses bounded exponential delay with deterministic 0.8–1.2 jitter; default
  maximum attempts is three.
- Exhaustion enters explicit `dead_letter`; error detail is not persisted and the
  error code is sanitized.
- `python -m app.worker replay --job-id <uuid> --actor <operator>` is the explicit
  audited replay path. Only a dead-letter row can be replayed.
- `python -m app.worker status` exposes content-free counts and oldest ready-job
  age for monitoring/alert integration.
- The worker defaults to concurrency 1 (bounded 1–4), stops claiming on shutdown,
  drains for a configured grace period, then cancels and safely releases leases.

## Verification evidence

| Gate | Result |
|---|---|
| Focused BE-01 + consent/privacy/source tests | PASS — 26 tests (worker unit batch 7; complete focused batch covered PostgreSQL and existing security tests) |
| PostgreSQL outbox/lease/restart tests | PASS — rollback atomicity, duplicate enqueue, restart, concurrent claim, expiry/reclaim, stale completion, retry/DLQ and audited replay |
| Relevant unit + integration regression | PASS — 477 tests in isolated Linux Compose |
| Alembic clean upgrade | PASS — empty isolated PostgreSQL upgraded through `8b9d0e1f2a3c` |
| Alembic rollback/forward + drift | PASS — downgrade to `7a8c9d0e1f2b`, upgrade head, `alembic check` reported no operations |
| Changed-lines Ruff | PASS |
| Legacy Ruff debt ratchet | PASS — 2,852 findings, baseline 2,914 (no increase) |
| mypy application | PASS — 284 source files |
| pip dependency check | PASS — no broken requirements |
| Production Compose schema validation | PASS with deployment-secret placeholders only; no secret value logged or committed |
| Protected prompt diff audit | PASS — prompt wording unchanged; only failure propagation/idempotency plumbing changed in prompt-owning modules |

## Deferred, explicitly out of BE-01

- `BE-03`: atomic guild/channel counters, cache-after-commit coordination and
  broader shared-state concurrency.
- `BE-02`: provider capability failover/circuit-breaker redesign.
- `OPS-02`: OpenTelemetry exporter, dashboards and alert delivery. BE-01 exposes
  content-free queue snapshot hooks only.
- Retention/purge policy for completed job audit rows belongs to operational data
  lifecycle work; user deletion already cascades its own job rows.
- Legacy Ruff debt and unrelated ingestion/readability debt remain governed by
  their existing ratchet/tasks.

## Refreshed acceptance matrix

| Requirement | Status | Evidence |
|---|---|---|
| Transactional producer/outbox atomicity | PASS | Same request session/transaction; rollback integration test |
| Durable queue and restart recovery | PASS | Alembic-owned PostgreSQL state; new queue instance claims committed pending job |
| Lease, renewal and stale-worker fencing | PASS | Concurrent claim, heartbeat, expiry/reclaim and stale-token tests |
| Bounded retry/backoff and DLQ | PASS | Retry schedule/exhaustion and terminal-state test |
| Controlled replay and observability | PASS | Actor/timestamp replay audit and content-free queue snapshot/CLI |
| Idempotent side effects | PASS | Unique enqueue key; deterministic memory/image IDs; summary overwrite semantics |
| Separate worker and graceful shutdown | PASS | Dedicated Compose service/entrypoint and drain/release test |
| Payload privacy | PASS | Typed versioned reference payloads and negative secret/size tests |
| Alembic-only ownership | PASS | Migration rollback/forward and drift verification |
| Isolated verification / protected prompts | PASS | Linux Compose 477 PASS; prompt diff audit clean |

**BE-01 FORMAL CLOSURE: PASS.**
