# RAG-05 formal offline raw_wiki ablation

## Scope and provenance

- Dataset: `rag05-raw-wiki-golden-v1-draft` (human-approved)
- Approved-content SHA-256: `01cababd2e9912a1b435869afc500dc44d727d045f6bafe868c3be4bc6004976`
- Corpus snapshot SHA-256: `ae0d1f3a18b650a5741bf9f7b404ed90950ce15c354049301f79204f7c21a9bb`
- Provider/model: Voyage `rerank-3-lite`
- Cases: 83 total; 81 answerable; 2 approved abstentions
- Candidate documents: 214; reranker maximum: 15
- Retrieval mode: offline raw_wiki page snapshot
- Production equivalent: **false**

No query, evidence identity, label, retrieval parameter, reranker parameter, corpus,
or index was changed for this run. Only public, human-approved raw_wiki text entered
the provider boundary; the existing adapter applied PII redaction.

## Answerable-slice quality

| Metric | Dense+sparse+RRF | Voyage rerank | Absolute change |
|---|---:|---:|---:|
| Hit@1 | 0.790123 | 0.950617 | +0.160494 |
| Hit@3 | 0.975309 | 1.000000 | +0.024691 |
| Hit@5 | 1.000000 | 1.000000 | 0.000000 |
| MRR@10 | 0.882716 | 0.975309 | +0.092593 |
| Context precision | not evaluable — label incomplete | not evaluable — label incomplete | — |

Outcome counts over all 81 answerable cases:

- Improved: 15
- Unchanged: 65
- Degraded: 1 (`rw-034`)
- First-stage retrieval misses: 0

The MRR relative improvement is 10.49%. A deterministic paired bootstrap over the
81 case-level reciprocal ranks (10,000 iterations, seed `20260906`) produced:

- Baseline MRR@10 95% interval: `[0.830247, 0.931070]`
- Voyage MRR@10 95% interval: `[0.950617, 0.993827]`
- Paired MRR delta 95% interval: `[0.045267, 0.143004]`

Hit-rate Wilson 95% intervals:

- Baseline Hit@5: `[0.954722, 1.000000]`
- Voyage Hit@5: `[0.954722, 1.000000]`
- Baseline Hit@1: `[0.689346, 0.864628]`
- Voyage Hit@1: `[0.879798, 0.980631]`

## Abstention handling

Both abstention cases (`rw-082`, `rw-083`) completed provider execution but were
excluded from Hit@K, MRR, and first-stage-miss denominators. No reciprocal rank was
assigned. Final-answer abstention quality remains
`not_evaluable_at_retrieval_stage`; no abstention precision or recall is claimed.

## Provider and cost telemetry

| Item | Result |
|---|---:|
| Provider calls | 83 |
| Validated Voyage responses | 83 |
| 429 | 0 |
| Timeout | 0 |
| Provider error | 0 |
| Invalid response | 0 |
| Fallback | 0 |
| Privacy/policy rejection | 0 |
| Estimated processed tokens | 313,439 |
| Conservatively reserved tokens | 391,827 |
| Estimated cost | USD 0.00626878 |

Fallback output was never counted as Voyage output. All 83 case results have
independent pacing, provider HTTP, reranker-stage, and total-retrieval timing.

## Latency

| Timing | Min (ms) | Mean (ms) | p50 (ms) | p95 (ms) | Max (ms) |
|---|---:|---:|---:|---:|---:|
| Provider HTTP | 260.563 | 419.287 | 402.040 | 593.278 | 905.555 |
| Reranker total, including pacing | 267.978 | 36,819.499 | 59,417.089 | 60,000.615 | 60,062.401 |
| Total retrieval with reranker | 367.105 | 36,960.457 | 59,488.704 | 60,104.268 | 60,224.019 |
| Baseline retrieval | 37.320 | 140.947 | 88.415 | 161.607 | 2,818.135 |

Tier-0 pacing was measured separately:

- Total wait: 3,019,930.345 ms
- Mean: 36,384.703 ms
- p50: 58,998.611 ms
- p95: 59,531.778 ms
- Paced cases: 61/83

Pacing-inclusive times are diagnostic only and are not used as provider HTTP
latency conclusions.

## SRS acceptance comparison

| Requirement | Evidence | Status |
|---|---|---|
| NFR-RAG-006 Hit@5 >= 0.90 | Baseline 1.00; Voyage 1.00 | PASS |
| NFR-RAG-006 MRR@10 >= 0.80 | Baseline 0.882716; Voyage 0.975309 | PASS |
| RAG-05 meaningful improvement | MRR +0.092593; paired delta CI excludes zero | PASS for this offline sample |
| NFR-PERF-006 rerank p95 <= 250 ms | Provider HTTP p95 593.278 ms for 15 candidates | **FAIL** |
| NFR-RAG-003 context recall >= 0.85 | Not separately annotated/evaluated | NOT EVALUABLE / OPEN |
| NFR-RAG-004 context precision >= 0.75 | Top-k labels incomplete | NOT EVALUABLE / OPEN |
| NFR-RAG-007 abstention precision >= 0.90 | Retrieval-only harness | NOT EVALUABLE / OPEN |
| NFR-RAG-001/005 grounding and citation | No answer generation in this ablation | NOT EVALUABLE / OPEN |
| NFR-RAG-008 leakage | Public-approved scope and zero policy rejection; adversarial leakage suite not part of this run | OPEN |
| Provider failure/fallback | 0 errors and 0 fallback | PASS for this run |
| Production retrieval parity | Explicitly `production_equivalent=false` | OPEN |

## Decision

The formal offline ablation execution is complete and shows a statistically positive
MRR improvement, but **RAG-05 remains NO-GO**. Provider HTTP p95 violates
NFR-PERF-006, several required quality/safety metrics are not evaluable with the
current retrieval-only/incompletely annotated dataset, and this run is not proof of
production retrieval parity.

The machine-readable per-case evidence is stored in
`reports/RAG05_Raw_Wiki_Golden_V1_Voyage_Ablation.json`.
