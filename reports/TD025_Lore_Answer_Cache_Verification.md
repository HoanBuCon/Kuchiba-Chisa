# TD-025 — Versioned, tenant/ACL-safe lore-answer cache correctness

Date: 2026-09-12
Branch: `reliability/p2-td025-cache-correctness`
Base: `HBC` at `0fb8cd7`
Traceability: `TD-025`, `NFR-REL-004`, `NFR-PERF-009`, `RAG-06`, `BE-02`, `BE-03`

## Closure status

**PASS / RESOLVED.** Final lore answers are now cached only through a
versioned, deterministic, authorization-bound contract. A cache hit cannot
reuse an answer from another active corpus snapshot, generation policy, prompt
semantic version, grounding contract, principal, tenant, or channel. Cached
answers retain only server-owned citation identifiers and an opaque access
receipt; legacy and malformed values fail closed as cache misses.

No database migration, production cache flush, active corpus/index mutation,
paid provider call, or protected-prompt edit was made.

## Audit findings and gap matrix

| Dimension | Previous behavior | Correctness/security risk | Implemented change |
|---|---|---|---|
| Read eligibility | Cache ran only for exactly `[LORE]`, while the active classifier normally composes `LORE` with `KNOWLEDGE_OR_TASK` | Intended cache path was mostly dead and its behavior was not exercised on the real intent composition | Typed eligibility accepts only the bounded lore set `{LORE, KNOWLEDGE_OR_TASK}` and still excludes small talk, image, web, and tool-output paths |
| Key construction | `MD5(cleaned_query)` under a global key | Stale answer and unauthorized cross-scope reuse | Canonical correctness components are SHA-256 fingerprinted into bounded key `chisa:answer_cache:lore:lore-answer-v2:<digest>` |
| Corpus/index version | Absent | Answer/citations could survive an atomic corpus publish | One authoritative Qdrant alias snapshot binds all three managed lore aliases to immutable versioned physical targets |
| Generation identity | Absent | Model/routing changes could reuse semantically incompatible output | Opaque BE-02 generation-policy fingerprint includes logical profile, primary/enabled/fallback routing, enabled models, and purpose eligibility |
| Prompt semantics | Absent | Context/prompt-semantic changes could reuse incompatible output | Opaque configured prompt semantic version plus a hash of output-relevant dynamic prompt inputs; no raw prompt is stored |
| Grounding contract | Absent | A cache hit could bypass a newer RAG-06 contract | Grounding/citation contract version and answer-schema version are identity components |
| Principal/tenant/ACL | Absent | Global cross-user or cross-tenant answer reuse | Server-derived principal, tenant, channel, and community scope are fingerprinted; every cached citation carries a separately validated opaque ACL binding |
| Value contract | Raw answer string | No provenance, expiry, ACL, or compatibility validation | Strict immutable Pydantic `lore-answer-v2` value with exact identity components, timestamps, verified state, and citation receipts |
| TTL | Fixed 24 hours in the stage | Not typed or centrally bounded | Typed setting, default 86,400 seconds, bounded to 60–604,800 seconds; entry expiry is validated independently of Redis TTL |
| Write eligibility | Any non-fallback string | Rejected, ungrounded, abstained, private-memory-mixed, or incomplete results could be published | Only completed `submit_grounded_answer` results with verified grounding, non-abstention, unique valid citations, and lore-only evidence are cacheable |
| Publication race | No version revalidation | Alias could change between read and write | Active alias snapshot and complete identity are recomputed immediately before atomic Redis `SET`; mismatch is `stale_version` and no write occurs |
| Legacy/malformed values | Fallback strings were deleted; other raw values were reused | Mutation at read time and unsafe compatibility assumptions | Invalid/current-incompatible values remain untouched and are treated as `malformed`/miss |
| Observability | Logged key and raw cached answer in tracker | Query/answer disclosure | Only typed outcome and schema metadata are tracked; operational logs use a short opaque identity fragment and sanitized exception type |

## Before and after identity

Before:

```text
chisa:answer_cache:lore:<md5(cleaned_query)>
```

After:

```text
stable correctness components
  -> canonical JSON
  -> SHA-256
  -> chisa:answer_cache:lore:lore-answer-v2:<digest>
```

The canonical components are:

1. normalized rewritten query (or cleaned-query fallback), stored only as a fingerprint;
2. all active lore alias-to-versioned-collection targets;
3. BE-02 logical generation policy fingerprint;
4. `submit-grounded-answer-v1` answer schema;
5. configured prompt semantic version and hashed dynamic prompt inputs;
6. configured RAG-06 grounding/citation contract version;
7. effective principal/tenant/channel/community authorization fingerprint.

Language and answer mode are not duplicated as ad-hoc key fields: language,
conversation state, persona selection, community context, and memory policy
already participate in the dynamic prompt fingerprint. Transient deadlines,
breaker state, quotas, secrets, and disabled-provider model names are excluded
because they do not define a successfully delivered answer's semantics.

## Corpus and citation correctness

`QdrantService.active_lore_corpus_identity()` reads one Qdrant alias snapshot
and requires complete, valid, versioned targets for `character_lore`,
`world_lore`, and `story_lore`. Missing, logical/unversioned, or malformed
targets disable the cache rather than guessing a corpus identity.

The read snapshot is saved only as an opaque fingerprint. Before publication,
the write stage resolves the aliases again and recomputes the entire identity.
An alias swap or any other output-relevant context change prevents stale
publication. The immutable physical collections and atomic aliases established
by the ingestion lifecycle are reused; no parallel corpus-version mechanism was
introduced.

Only citation IDs already accepted by the server-owned RAG-06 output boundary
are stored. Every ID must be unique, present in the prompt's retrieved evidence,
and backed by lore-only evidence. Citation access scope is retained as an
opaque binding over scope/subject/tenant/channel and revalidated against the
current request before delivery. Corpus fingerprint equality prevents IDs from
another corpus publication from being served.

There is no independent ACL revision object in the current architecture. Lore
ACL payload changes are published as corpus/index changes, so the authoritative
alias-target fingerprint is the applicable ACL revision boundary. The exact
principal/tenant/channel binding provides a second authorization check.

## Generation and prompt handling

`generation_policy_fingerprint()` derives identity from the BE-02 routing and
capability configuration that can determine a successful result: logical
profile, primary provider, enabled providers, fallback order, enabled model
names, and enabled purpose eligibility. API keys, runtime health, rate state,
deadlines, and disabled-provider model settings are excluded.

Protected prompt text is neither read nor rewritten by the cache contract.
Prompt semantics use the opaque setting
`LORE_ANSWER_CACHE_PROMPT_VERSION=context-builder-v1`; dynamic prompt inputs
are canonicalized and hashed. Raw system/persona/relationship prompt content,
queries, history, principal IDs, and private conversation content do not appear
in Redis keys, cache metadata, or tracker fields.

Operators must bump the corresponding opaque version when an approved prompt
or grounding-contract semantic change is deployed. This explicit operational
versioning preserves protected-content handling without hashing or persisting
the protected prompt itself.

## Read, write, legacy, and degraded behavior

- Read failures in Redis or corpus identity resolution become a normal cache
  miss; the existing BE-02 call budget remains unused until the normal gateway
  path executes.
- A valid hit sets the accepted answer/citations and bypasses the provider
  without consuming `LLMCallBudget`.
- Legacy strings, invalid JSON, unknown/missing fields, expired values, identity
  mismatches, and ACL mismatches are never partially reused or rewritten.
- Safe abstentions are deliberately not cached because current RAG-06
  abstention receipts have no citation set and may change with corpus coverage.
- Provider errors and incomplete streaming executions cannot reach the cache
  update stage. The stage additionally requires a fully assembled, verified,
  non-abstained generation receipt.
- Redis `SET` publishes the complete immutable JSON value atomically. Concurrent
  identical writes may race but leave one valid current-format value; no global
  lock, process-local correctness lock, or second distributed-lock system was
  added.

## Verification evidence

### Deterministic and regression tests

- TD-025 focused contract plus RAG-06/auth/BE-02/BE-03/SSE regression batch:
  **112 passed**, 1 pre-existing Qdrant insecure-test-connection warning.
- Entire host unit suite: **542 passed**, 2 warnings.
- Isolated Linux Docker Compose gate:
  - Alembic `upgrade head`: **PASS**;
  - Alembic drift check: **PASS**, `No new upgrade operations detected`;
  - mypy: **PASS**, 292 source files;
  - `pytest tests/unit tests/integration -q`: **558 passed**, 2 warnings.

The first Compose attempt could not publish host port `55432` because the local
IDE owned it. The successful run used a temporary, subsequently deleted Compose
override that removed only host port publication. PostgreSQL, Redis, Qdrant,
the test container, internal service hostnames, environment, migration command,
typecheck, and test command were unchanged. The disposable project was removed
with its volumes and network after verification.

### Static and repository gates

- changed-lines Ruff: **PASS** against `HBC`;
- new-file Ruff: **PASS**;
- full-repository Ruff debt ratchet: **PASS**, 2,817 findings <= baseline 2,914,
  with zero blocking-rule findings;
- `python -m mypy app`: **PASS**, 292 source files;
- `python -m pip check`: **PASS**;
- `python -m compileall -q app`: **PASS**;
- `git diff --check`: **PASS**;
- no schema migration added; isolated Alembic drift verification: **PASS**.

### Acceptance matrix

| Acceptance criterion | Evidence | Result |
|---|---|---|
| Same request/version/scope hits and avoids provider | Focused test validates answer/citations, unchanged budget, and provider `execute` not awaited | PASS |
| Corpus/index publish invalidates answer | Alias-target fingerprint change and read/write alias-race tests | PASS |
| Generation/profile change invalidates answer | Enabled-model/routing fingerprint and cache-miss tests | PASS |
| Prompt semantics change invalidates answer | Opaque prompt version and dynamic-context fingerprint tests | PASS |
| Grounding contract change invalidates answer | Contract-version cache-miss test | PASS |
| Tenant/effective ACL cannot cross scopes | Principal, tenant, channel, same-scope, and forged broader-receipt tests | PASS |
| Legacy/malformed/expired fail safely | Raw string, invalid/current-incomplete JSON, and expiry tests; no mutation | PASS |
| Only deliverable results are cached | Verified answer passes; rejected, empty, abstained, uncited, and memory-mixed results do not write; explicit provider-error and interrupted-stream pipelines stop before publication | PASS |
| Cached citations remain server-owned and authorized | Citation subset/uniqueness and access-binding validation tests | PASS |
| Concurrent writes preserve current schema | Concurrent publication parses as one valid immutable v2 entry | PASS |
| RAG-06 remains intact | Grounding/citation/output-contract regression suite | PASS |
| BE-02 remains intact | Gateway regression suite, no budget use on hit, normal miss budget unchanged | PASS |
| BE-03 remains intact | State-handler regression and isolated PostgreSQL/Redis integration suite | PASS |
| Protected prompts unchanged and undisclosed | Git blob/hash audit plus cache/tracker sentinel test | PASS |

## Security and architecture review

**PASS.** Domain policy owns cache eligibility, deterministic identity, typed
value validation, and authorization receipt checks. Infrastructure owns Qdrant
alias resolution and Redis atomic storage. Composition injects the existing
provider implementations; route/controllers contain no cache business rule.

The design is deliberately conservative: cache identity is principal-bound even
for public lore, favoring authorization safety over maximal global hit rate.
Private-memory-mixed prompts are not cached. Provider/cache failures do not
become successful synthetic answers. No secrets or raw sensitive inputs are
persisted in the new contract.

## Protected prompt audit

Git blobs match `HBC` for all five protected paths:

| Protected path | Git blob | SHA-256 |
|---|---|---|
| `app/domain/services/context_builder.py` | `daa215504541d1dc2cc6b4c110aed5de685cee3a` | `5e009e3337cff67440f8293295a8a3baf259866e1e9d17070401716e62b547f0` |
| `app/domain/services/persona_loader.py` | `543fca426ad8cb29ed191c35bf1de04305ed6640` | `d95435e571ebabcebf6c302ffa6162c87a9c938713da9ce68b074464fd063414` |
| `data/lore/character_lore/chisa_personality.md` | `892d5da5a9a531f7175a8bc232783494aa06eabe` | `dd1aef9a310f424464aee3ec00000105d3cfe016bef250a4236630c80bcb0510` |
| `data/lore/relationship_lore/rover.md` | `92078b6d8be8348ac76fe1d609158d0e72c40d25` | `333d301a71e23887ef68d4a252bf18ea027bdda9f392364cda85ea57482f3922` |
| `data/lore/relationship_lore/sumika.md` | `a9e0e2325433a373912cc5b264b1250127176127` | `ab308bb2a1744717a507fc2196e06537ba103c49b5d31353763eb997256cdbcb` |

Result: **5/5 unchanged**. A regression test also proves a protected-content
sentinel cannot appear in cache keys, values, or pipeline-tracker metadata.

## Residual technical debt and P2 status

- Cache-stampede optimization is intentionally not implemented; it is not a
  current correctness requirement and Redis writes are atomic.
- Cache hit-rate/cost/SLO dashboards and distributed telemetry remain `OPS-02`.
- Prompt and grounding semantic-version bumps remain an explicit release
  responsibility; future `OPS-02` instrumentation should expose the opaque
  versions without prompt text.
- Existing Ruff findings remain governed by the non-increasing legacy-debt
  ratchet; TD-025 introduced no changed-line or blocking-rule debt.

P2 completed: `DB-01`, `BE-01`, `BE-02`, `BE-03`, and `TD-025`.
P2 remaining: `OPS-02`, `OPS-03`, `CH-01`, and `OPS-04`.

Recommended next task: **OPS-02 OpenTelemetry/SLO**. It is not started by this
closure.
