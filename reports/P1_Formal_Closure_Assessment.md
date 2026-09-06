# P1 Formal Closure Assessment

Date: 2026-09-06 (Asia/Saigon)
Branch: `hardening/p0-p1-remediation`
Source of truth: `reports/SRS_Kuchiba_Chisa.md` v1.1

## Decision

`P1 FORMAL CLOSURE: PASS`

Every P1 backlog row is supported by passing implementation, evaluation and
security evidence. Retrieval-only evidence was not reinterpreted as generation,
citation, abstention, security or ingestion-release evidence; those obligations
were verified independently.

## Acceptance matrix

| Task | Status | Definition of Done | Evidence retained | Exact remaining gap |
|---|---|---|---|---|
| `TD-036` / `NFR-OPS-006`, `NFR-OPS-006A` | **PASS** | Versioned Ruff baseline decreases by reviewed batches; changed/new findings and semantic/security/correctness findings block; full debt cannot increase. | `.ci/ruff_debt_baseline.json`; `scripts/ruff_debt_ratchet.py`; CI changed-lines and full-ratchet jobs; `reports/TD036_Ruff_Debt_Ratchet.md`; 4 focused tests passed. Versioned baseline is 2,914 versus historical 3,861 with zero blocking semantic findings. | None for ratchet enforcement. Legacy debt remains subject to incremental reduction; PASS does not mean full-repository Ruff-clean. |
| `RAG-03` / `FR-RAG-003`, `FR-RAG-006` | **PASS** | Typed evidence carries provenance, ACL, source/corpus version, spans, and score decomposition through retrieval and context selection. | `app/domain/models/evidence.py`; `app/domain/services/rag/retriever_lore.py`; `app/domain/services/rag/pipeline.py`; `tests/unit/test_rag_evidence_model.py`. Focused P1 run passed. | None for this task's DoD. |
| `RAG-04` / `FR-RAG-004`, `NFR-RAG-003`, `NFR-RAG-006` | **PASS** | Parallel dense+sparse/BM25, calibrated RRF, timeout behavior, and evaluated hybrid retrieval. | Hybrid implementation and timeout/fusion unit coverage in `app/domain/services/rag/lore_fusion.py`, `tests/unit/test_hybrid_lore_retrieval.py`; frozen production-equivalent retrieval evidence in `reports/RAG05_Staging_Qdrant_Retrieval_Evaluation.{md,json}`; accepted current-state evidence in the P1 closure directive. | None for this task's DoD; the accepted benchmark is not rerun or invalidated. |
| `RAG-05` / `FR-RAG-005`, `NFR-PERF-006`, `NFR-RAG-004`, `NFR-RAG-006` | **PASS** | Remote reranker improves frozen hybrid baseline; p95 provider HTTP latency ≤750 ms; timeout/fallback/privacy/adversarial behavior; approved context precision. | Jina staging: 83/83 valid, Hit@5 0.975309, MRR@10 0.909465, HTTP p95 413.085 ms, zero fallback; `reports/RAG05_Staging_Jina_Ablation.{md,json}`. Provider-boundary tests/report pass. Human review: 405/405 relevant, context precision 1.0; `rag05_context_precision_review_v1.*`. `TD-037` is resolved. | None for the reranking task's DoD. Generation/citation/final-answer abstention remain separate `RAG-06` obligations and are not inferred from this PASS. |
| `RAG-06` / `FR-RAG-008`, `FR-RAG-009`, `FR-RAG-011`, `NFR-RAG-001`, `NFR-RAG-002`, `NFR-RAG-005`, `NFR-RAG-007` | **PASS (`TD-038` resolved)** | Claim-evidence verification, correct citations, fail-closed abstention, and all quantitative thresholds with evaluator version, confidence interval, sample size, and human audit. | Project owner `HoanBuCon` approved 38/38 frozen v2 cases. `reports/RAG06_Final_Acceptance.md` records faithfulness 44/44 = 1.0 with zero critical unsupported claims, answer relevance 31/36 = 0.861111, citation correctness 64/64 = 1.0, and approved no-answer abstention precision 2/2 = 1.0 with Wilson intervals. Frozen generation/evidence content SHA-256 remained `333005f…e11ebd`; protected prompts and corpus/index remained unchanged. | None for the formal DoD. `rw-003` and `rw-044` false abstentions, three partial-relevance cases, raw-wikitext readability debt and the wide 2-case abstention CI remain explicitly recorded as non-blocking debt. |
| `SAFE-01` / `SEC-RAG-001`, `SEC-RAG-002`, `SEC-RAG-003`, `SEC-RAG-008`, `NFR-RAG-008` | **PASS** | Multi-layer user/RAG/web/memory/image injection protection, leakage canary, and mandatory VN/EN adversarial suite with zero leakage. | `safe01_adversarial_v1.json`; `test_safe01_adversarial_suite.py`; existing injection, vision, leakage-canary and authorization regressions; `reports/SAFE01_Adversarial_Verification.md`. Combined focused suite: 46 passed, 0 failed, zero prompt/cross-tenant leakage. | None for this task's DoD. |
| `SAFE-02` / `SEC-DATA-001`, `SEC-DATA-002`, `SEC-DATA-003`, `SEC-DATA-006` | **PASS** | PII classification/masking before providers and persistence; consent-aware memory retention/withdrawal; privacy regressions. | `PiiRedactor`, provider redaction stage, consent policy/route, bounded retention and withdrawal paths; 9 focused tests in `tests/unit/security/test_pii_consent_policy.py`; all passed. | None for this task's P1 DoD. Broader legal-market documentation remains `NFR-OPS-008`, not silently claimed here. |
| `ING-01` / ingestion data-plane item 1 | **PASS** | One canonical orchestrator/CLI and legacy pipeline removed only after parity. | `reports/ING01_Canonical_Parity_Verification.md`; deterministic fact/revision/identity/span/ACL fixture; canonical orchestration, vector acknowledgement and ING-02 release evidence; operator/CLI negative regressions. `run-dag` is the sole standard entry point and accepts only approved source UUID plus physical staging collection. | None for this task's DoD. Raw-wikitext presentation cleanup remains non-blocking quality debt and does not restore a second ingestion path. |
| `ING-02` / ingestion data-plane items 2–3 | **PASS** | Versioned dense+sparse+parent staging; checksum/ACL/golden gates; atomic alias swap and verified rollback. | Real isolated PostgreSQL/Qdrant integration in `test_ing02_publish_rollback.py`; `reports/ING02_Isolated_Publish_Rollback_Verification.md`. Publish and rollback both completed, alias returned to retained prior, five durable audit actions persisted, and both physical collections were retained. | None for this task's DoD. Production/active data was not touched. |
| `ING-03` / ingestion data-plane item 4 | **PASS** | Source registry, trust/license/quarantine, poison/PII/secret scan, curator approval and audit. | Existing governance, poison gate and immutable exception tests plus canonical PII/secret scanning in `ValidationStage`; `reports/ING03_Source_Governance_Verification.md`. Governance/security suite: 28 passed; parser/sanitizer suite: 29 passed. | None for this task's DoD. Raw evaluation-corpus noise remains visible and is tied to `ING-01` canonical-path parity rather than hidden by this closure. |

## Verification performed

- Python: `3.11.9` using the repository's absolute `venv` interpreter.
- Focused canonical ingestion suite: **134 passed**, 0 failed, with one
  service-backed benchmark run separately.
- Real isolated Qdrant benchmark plus PostgreSQL/Qdrant publish-and-rollback:
  **2 passed**, 0 failed.
- Full repository test suite against isolated PostgreSQL, Redis and Qdrant:
  **567 passed**, 0 failed.
- Changed-lines Ruff: PASS. Ruff on all untracked/new Python files: PASS.
- Ruff full audit ratchet: **2,866 findings <= committed baseline 2,914**, below
  historical 3,861; zero findings in the explicit
  semantic/security/correctness blocking set.
- Mypy: success across 274 application/CLI source files.
- Pip dependency check: no broken requirements.
- Linux Docker test image build: PASS. Container smoke: Python 3.11, `pip check`
  PASS, 12 focused tests passed.
- Protected prompt integrity: all **5/5** frozen system/persona/relationship
  content SHA-256 values matched; no protected content path was modified.
- No provider benchmark was rerun; no production corpus, collection, alias, or active data was mutated.

## Interpretation of the reviewed raw-wiki noise

The user's approval that all 405 returned items answer their queries is valid relevance evidence for `NFR-RAG-004`. The observed MediaWiki residue and broken chunk boundaries are a different quality dimension. They do not retroactively change the 405 relevance labels, but they can lower final-answer faithfulness, citation readability, and ingestion publish quality. They therefore remain tracked under `ING-01`/`ING-03` and must be represented in the future `RAG-06` generation evaluation rather than hidden by relabelling retrieval results.

## Closure limitations retained

- The Ruff ratchet PASS does not mean the legacy repository is fully Ruff-clean.
- RAG-06 still records two false abstentions, three partially relevant answers,
  raw-wikitext readability debt and a wide abstention confidence interval based
  on two approved no-answer cases.
- The single-node P1 verification is not evidence for P2 HA/load/restore SLOs.

## RAG-06 disposition

Project owner `HoanBuCon` approved the complete frozen 38-case v2 review set. All current point thresholds pass without waiver, confidence intervals and limitations remain visible, and `TD-038` is resolved. `RAG-06` is **PASS**. Protected prompts were not changed.
