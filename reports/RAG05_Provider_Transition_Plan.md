# RAG-05 Provider Transition and Deferred Verification Record

| Field | Value |
|---|---|
| Record ID | `TD-037` |
| Requirement/task | `RAG-05` production-equivalent remote reranker ablation |
| Decision timestamp | `2026-09-06T03:47:15+07:00` |
| Approval authority | User/project owner, explicitly approved in the implementation session |
| Deferred provider/model | Voyage / `rerank-3-lite` |
| Status | **RESOLVED / CLOSED** |
| Next candidate | Jina hosted API / `jina-reranker-v3.5` |
| Closure timestamp | `2026-09-06T04:33:38+07:00` |
| Closure path | Exit condition 2 — approved alternative provider on the same frozen production-equivalent candidates |

## Closure decision

`TD-037` is **RESOLVED/CLOSED**. Jina `jina-reranker-v3.5` completed the frozen production-equivalent staging ablation recorded in `reports/RAG05_Staging_Jina_Ablation.{md,json}`:

- approved fingerprint `01cababd2e9912a1b435869afc500dc44d727d045f6bafe868c3be4bc6004976`;
- corpus `raw-wiki-sha256:0efe04a586291c11c84c921a1839ac20be53f12c026e3ea2b43595e9a7d32c7a`;
- staging version `rag05eval_01cababd2e_20260905192227` and unchanged production-equivalent candidate path;
- 83/83 validated Jina responses, 0 HTTP 429, timeout, provider error, invalid response or fallback;
- Hit@5 `0.975309`, MRR@10 `0.909465` and provider HTTP p95 `413.085 ms` against the unchanged `750 ms` component threshold;
- staging namespace unchanged and approved golden-set content unchanged.

This satisfies the originally recorded second exit path without broadening it. The Voyage Tier-0 attempt and its 68/83 validated responses, 15 HTTP 429 responses and 15 fallbacks remain below as historical audit evidence. Closing `TD-037` does not select a production provider and does not mark overall `RAG-05` PASS.

## Decision and reason

Do not continue rerunning the frozen 83-case production-equivalent Voyage ablation under the current Tier-0 allowance of approximately 3 RPM and 10,000 TPM. The completed staging attempt showed long quota pacing and rolling-window boundary failures: 83 provider attempts yielded 68 valid Voyage responses, 15 HTTP 429 responses and 15 explicit deterministic fallbacks. Fallback rankings were not counted as Voyage output, so no formal Voyage aggregate was asserted.

This is an execution-practicality limitation of the current provider tier. It is not evidence of a dense/sparse/RRF, Qdrant, golden-set or provider-abstraction defect. It is neither a `RAG-05` PASS nor a reranker quality FAIL.

## Frozen evaluation identity

The following inputs remain immutable for the eventual rerun/comparison:

- Golden set: 83 human-approved cases, comprising 81 answerable and 2 abstention cases.
- Approved content SHA-256: `01cababd2e9912a1b435869afc500dc44d727d045f6bafe868c3be4bc6004976`.
- Corpus version: `raw-wiki-sha256:0efe04a586291c11c84c921a1839ac20be53f12c026e3ea2b43595e9a7d32c7a`.
- Staging version: `rag05eval_01cababd2e_20260905192227`.
- Staging pipeline fingerprint: `41a2cbe0acc39133bf5c6804363e10f2f5ced475dd10c96129de9e51aa24a102`.
- Retrieval: local E5-small dense plus Qdrant sparse/BM25, calibrated RRF, unchanged production-equivalent first-stage candidate path.
- Reranker input budget: unchanged production candidate pool and top 10–15 policy; no benchmark-specific candidate-count adjustment.

Production-equivalent first-stage retrieval is already verified by `reports/RAG05_Staging_Qdrant_Retrieval_Evaluation.{md,json}`. The staging namespace was isolated, no alias was published, and the active corpus/index was not mutated.

## Exit condition

`TD-037` may be closed only through one of these paths:

1. Voyage access is upgraded to practical RPM/TPM limits, then the exact frozen 83-case production-equivalent benchmark is rerun; or
2. an alternative remote reranker with user-approved prepaid/token-package capacity is formally benchmarked against the same frozen production-equivalent candidates. The preferred next candidate is Jina `jina-reranker-v3.5`.

Neither path permits post-hoc retrieval tuning, label changes, corpus/index mutation or a different candidate budget for benchmark advantage.

## Jina readiness at deferment time

The project already supports Jina without a provider-layer redesign:

- `app/domain/interfaces/reranker.py` retains the provider-neutral `ICrossEncoderReranker` port and remote/local boundary contract.
- `app/infrastructure/rag/api_cross_encoder_reranker.py` allowlists `https://api.jina.ai/v1/rerank`, sends the Jina `top_n`/`return_documents` request shape, validates response cardinality/index/finite scores, records provider HTTP latency and maps failures to typed unavailable outcomes.
- `app/infrastructure/rag/reranker_factory.py` selects Voyage, Jina or Cohere by typed configuration; deterministic fallback remains in the retrieval service.
- `app/config/settings.py` already defines `RERANKER_PROVIDER=jina`, `RERANKER_API_MODEL` and secret-only `JINA_API_KEY` configuration.
- The remote boundary retains PII redaction. Only public/approved lore is eligible; private memory, tenant-private data, user content/images, raw PII, protected prompts and sensitive evidence remain local.

Jina's current official hosted API documentation lists `jina-reranker-v3.5` as available through Jina API and describes it as request-schema compatible with v3. The hosted reranker endpoint is `https://api.jina.ai/v1/rerank`. As of this record, Jina documents 100 RPM/100,000 TPM/2 concurrent requests for free keys and 500 RPM/2,000,000 TPM/50 concurrent requests for paid keys. Billing is token-based; after the free allocation, users may purchase more tokens for the key. These are configuration-planning inputs, not contractual guarantees; actual account terms, balance and limits must be checked at provisioning time:

- <https://jina.ai/models/jina-reranker-v3.5/>
- <https://jina.ai/reranker/>

This goal detected only that a non-empty `JINA_API_KEY` is present in the local secret environment. Its value was not printed, logged or persisted, and its validity/token balance was not tested. No API key was created, no token was purchased, no billing setting was changed and no provider request was made for this transition record.

## Original formal benchmark plan — completed by closure evidence

1. User/project owner provisions `JINA_API_KEY` through environment/secrets and confirms sufficient free or purchased token capacity. Do not commit or log the key.
2. Keep automatic top-up disabled unless separately and explicitly approved. Do not assume the remaining token balance is a hard spend cap unless Jina contractually guarantees that behavior.
3. Freeze and verify the approved dataset fingerprint, corpus/staging version, candidate-pool fingerprints and all dense/sparse/RRF/candidate parameters before the first provider request.
4. Run baseline over the existing production-equivalent candidate path, then rerank the identical candidates with `jina-reranker-v3.5` and equivalent candidate count.
5. Enforce existing policy/redaction before outbound calls. On timeout, 429, provider error, invalid response or policy rejection, mark the case degraded and use deterministic hybrid fallback operationally; never count fallback output as Jina evidence.
6. Report Hit@1/3/5, MRR@10, improved/unchanged/degraded cases, unrecoverable candidate misses, provider HTTP latency, pacing separately where applicable, failures/fallbacks, processed tokens and actual/estimated cost.
7. Keep `context_precision = not_evaluable_label_incomplete` until top-k relevance annotation is complete. Keep abstention evaluation separate from positive ranking denominators.
8. Compare the complete Jina result against unchanged SRS quality, privacy, fallback and `NFR-PERF-006` thresholds. Optionally compare valid Voyage evidence only where execution semantics are methodologically compatible.

## Budget and billing controls

- No purchase, top-up, payment detail or provider-terms acceptance is authorized by this record.
- No automatic recharge is authorized.
- Runtime must retain timeout, maximum documents, request/token/cost budgets, telemetry and fail-closed deterministic fallback.
- Exhausted/invalid provider capacity must degrade to grounded hybrid retrieval, never silently to an ungrounded answer.

## Remaining `RAG-05` blockers after debt closure

- The deferred production-equivalent provider verification owned by `TD-037` is complete.
- Actual/token-package Jina cost remains not evaluable from the provider response and must be reviewed before a production-provider decision.
- Final-answer grounding/citations, final-answer abstention and adversarial leakage were not evaluated by this retrieval-stage benchmark.
- Existing non-evaluable relevance metrics remain OPEN and are not converted into PASS by this deferment.

## Local verification at deferment time

- Python: 3.11.9.
- Focused provider/factory/fallback tests: 15 passed; all provider interactions used local `httpx.MockTransport`, with no external provider call.
- Ruff on the changed Python test: passed.
- Mypy application gate: 272 source files passed.
- `pip check`: no broken requirements.
- Golden-set content, corpus/index, SRS quality thresholds and protected system/persona/relationship prompts were not changed.
