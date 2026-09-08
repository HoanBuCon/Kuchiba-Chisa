# BE-03 — Concurrency and state correctness

Date: 2026-09-08
Branch: `reliability/p2-be03-concurrency-state`
Traceability: `BE-03`, `TD-026`, `TD-027`, `TD-035`, `NFR-REL-005`, `NFR-REL-006`, `NFR-REL-008`

## Pre-implementation acceptance matrix

| Requirement | Required evidence | Initial state |
|---|---|---|
| Correct shared-state scope | Guild ambient keyed by guild; topic/buffer/counter keyed by guild + channel | FAIL — community request lock is speaker-scoped |
| Lost-update prevention | Concurrent writers retain every logical mutation | FAIL — ambient, topic buffer, counter and channel index use last-writer/RMW Redis writes |
| Version/fencing correctness | Stale summary/cache/lock owner cannot overwrite newer state | FAIL — no state revision or summary watermark; lock lease is not renewed |
| Cache after commit | DB commit atomically creates an outbox projection; Redis changes only after commit | FAIL — user and community Redis writes occur inside the uncommitted request transaction |
| Replay-safe cache/state | Duplicate events are idempotent; stale events are rejected | FAIL — caches have no revision/CAS semantics |
| Durable worker compatibility | BE-01 replay cannot regress shared state | FAIL — delayed summary jobs can overwrite newer summaries |
| Redis degraded behavior | Cache failure retries durably or fails closed where state ownership requires it | FAIL — chat locking returns a synthetic success token on Redis failure |
| TD-035 managed maintenance | Cleanup has lifecycle drain, bounded retry, coalescing and stale-target validation | FAIL — two raw `asyncio.create_task` paths swallow failures |
| Isolated multi-replica verification | PostgreSQL/Redis concurrency, rollback, replay and shutdown tests | Missing |
| Protected prompts unchanged | Final diff audit | Pending implementation |

## Audit findings and intended disposition

| Mutable path | Risk | BE-03 disposition |
|---|---|---|
| User stats and emotion persistence | Absolute read/modify/write can lose concurrent turns | Database-atomic mutation and monotonic state revision |
| User state cache | Cache can expose uncommitted or stale DB state | BE-01 outbox cache projection with revision-aware Redis CAS |
| Private conversation summary | Delayed job can overwrite a newer summary; cache propagation is non-durable | Source watermark CAS plus transactional cache-projection outbox |
| Community rolling buffer/counter/index | Redis GET/SET races lose turns/counts/channels | One atomic Redis state-store operation keyed by guild + channel, invoked only by a durable post-commit job |
| Guild ambient state | Concurrent speakers overwrite one another | Atomic guild-scoped versioned merge |
| Community topic summary | Slow/stale worker can erase new buffer entries or regress summary | Immutable source watermark and conditional publish; never trim post-watermark entries |
| Per-user chat lock | Redis errors fail open; fixed TTL has no renewal | Fail-closed acquisition, token renewal and ownership-verified release; DB/state CAS remains authoritative |
| Lore answer cache | Corpus/model/prompt/ACL cache-key completeness | Deferred under existing `TD-025`; not DB canonical state |
| Pipeline telemetry | Best-effort redacted diagnostics | Deferred to `OPS-02` |
| Image orphan and local quota cleanup | Raw untracked tasks, swallowed failures and stale/racing deletion | Node-local lifecycle supervisor with bounded retry, keyed single-flight and target revalidation (`TD-035`) |

## Final verification receipt

Status: **PASS**

### Implementation receipt

- PostgreSQL user statistics and emotion state use database-native atomic
  mutations. `state_revision`, `last_seen`, and emotion timestamps advance
  monotonically under concurrent writers.
- User-state and private-summary Redis projections are durable BE-01 outbox
  jobs. Consumers re-read canonical committed PostgreSQL state and publish with
  revision-aware Redis CAS; stale or replayed events cannot regress cache state.
- Conversation summary publication uses a source watermark and atomic compare
  and set. Delayed workers cannot overwrite summaries derived from newer input.
- Community rolling buffer, message count, processed event identity and guild
  ambient deltas are one Redis Lua transition. Topic summaries are generated
  from an immutable snapshot and conditionally published only while its source
  revision remains current.
- Per-user chat admission locks fail closed on Redis errors, use opaque owner
  tokens, renew while work is active, verify ownership immediately before
  commit, and release through a token-checked Lua operation. Correctness of
  shared mutations remains protected by PostgreSQL atomic updates or Redis Lua
  CAS rather than lease timing alone.
- Node-local image quota and Qdrant orphan cleanup now use a lifecycle-managed
  maintenance supervisor with keyed coalescing, bounded retry, content-free
  counters and graceful drain/cancel. Orphan deletion revalidates the exact
  point/payload fingerprint and local-file absence before a server-side
  identity-filtered delete.

### Acceptance evidence

| Acceptance criterion | Evidence | Result |
|---|---|---|
| Concurrent user/emotion updates retain all writes | 20 simultaneous PostgreSQL mutations; final count/revision `20`, monotonic timestamp, accumulated emotion | PASS |
| Concurrent community replicas retain all turns | Two Redis store instances, 25 concurrent events; 25 accepted, 50 messages, revision 25; replay rejected | PASS |
| Correct scope and independent channels | Two channels advance independently while guild ambient revision reaches 20 through atomic deltas | PASS |
| Stale summary/cache/lock owner is fenced | PostgreSQL summary CAS, Redis summary/cache CAS, owner-token renewal/release and pre-commit lease-loss tests | PASS |
| Cache is not visible before commit | Transactional outbox integration test observes no Redis projection before commit, then canonical projection after durable handling | PASS |
| Replay/late delivery cannot regress state | Duplicate community event, out-of-order cache event and duplicate summary job regression tests | PASS |
| Redis failure behavior is safe | Lock acquisition outage test returns no ownership token; chat refuses the protected transition | PASS |
| TD-035 work is lifecycle managed | Retry/coalescing/drain tests plus changed-point and exact-point orphan cleanup tests | PASS |
| Existing BE-01 durability remains intact | `test_be01_durable_queue.py` and `test_be01_job_sources.py`: 5 passed | PASS |
| Database schema is reproducible | Isolated `alembic upgrade head`, `alembic check`, schema tests: 11 passed | PASS |
| No protected prompt wording changed | Zero-context diff audit: only control-flow/call-site changes outside prompt literals | PASS |

### Verification commands and results

- Full Windows suite: `python -m pytest -q` — **610 passed**, 9 warnings.
- Focused BE-03 PostgreSQL/Redis integration: **8 passed**.
- Focused state/schema unit batch: **27 passed**.
- Focused TD-035 lifecycle/image batch: **19 passed**.
- BE-01 durable queue/source regression: **5 passed**.
- Linux Compose test target: **495 passed**, 2 warnings.
- `python -m mypy app` — **PASS**, 288 source files.
- changed-lines Ruff gate — **PASS**.
- new-file Ruff gate — **PASS**.
- Ruff legacy ratchet — **PASS**, current 2,832 <= baseline 2,914.
- `python -m pip check` — **PASS**.
- Alembic isolated upgrade/drift verification — **PASS**, no new upgrade
  operations after head `9c0e1f2a3b4d`.

Warnings are pre-existing Qdrant insecure-test-connection, Alembic configuration
deprecation, pytest collection/return warnings and do not change BE-03
correctness. Test infrastructure remained restricted to the disposable
`kuchiba_test` PostgreSQL/Redis/Qdrant stack; no production collection, alias or
database row was mutated.

### Architecture review

**PASS.** Domain contracts describe mutations, summaries, background payloads
and community-state operations without provider SDK types. Infrastructure owns
SQLAlchemy, Redis Lua and Qdrant cleanup details. Request orchestration performs
no direct cache write-through of uncommitted canonical state. BE-01 remains the
single durable background execution mechanism; the node-local supervisor is
limited to reconstructable maintenance and is not a second business queue.

### Residual risks outside BE-03

- Lore-answer cache version/ACL completeness remains `TD-025`.
- Broader observability/SLO instrumentation remains `OPS-02`.
- Legacy Ruff findings remain governed by `TD-036`; the baseline decreased and
  no new debt was admitted.
