# RAG-05 Production-Equivalent Staging Voyage Ablation

- Executed at: `2026-09-05T20:39:06.085107+00:00`
- Dataset fingerprint: `01cababd2e9912a1b435869afc500dc44d727d045f6bafe868c3be4bc6004976`
- Corpus version: `raw-wiki-sha256:0efe04a586291c11c84c921a1839ac20be53f12c026e3ea2b43595e9a7d32c7a`
- Staging version: `rag05eval_01cababd2e_20260905192227`
- Production-equivalent scope: first-stage retrieval only

## Quality

- Baseline: `{"context_precision": "not_evaluable_label_incomplete", "hit_at_1": 0.679012, "hit_at_3": 0.901235, "hit_at_5": 0.950617, "mrr_at_10": 0.788889}`
- Voyage: `null`
- Improved/unchanged/degraded: `19` / `46` / `1`
- First-stage misses: `['rw-013', 'rw-035', 'rw-041', 'rw-060']`
- Recovered into top-k: `['rw-013', 'rw-041']`
- Context precision: `not_evaluable_label_incomplete`
- Abstention: `not_evaluable_at_retrieval_stage`

## Provider and latency

- Telemetry: `{"calls": 83, "estimated_cost_usd": 0.00336012, "failure_counts": {"invalid_response": 0, "provider": 0, "rate_limit": 15, "timeout": 0, "unavailable": 0}, "fallback_count": 15, "privacy_policy_rejection_count": 0, "processed_token_estimate": 168006, "reserved_token_estimate": 200337, "validated_responses": 68}`
- Provider HTTP: `{"max": 519.13, "mean": 331.464, "min": 231.891, "p50": 324.276, "p95": 446.094}`
- Pacing: `{"mean": 19218.419, "p50": 200.462, "p95": 58953.794, "paced_cases": 69, "total": 1595128.792}`
- Reranker total: `{"max": 59849.868, "mean": 19535.017, "min": 236.711, "p50": 476.325, "p95": 59336.112}`
- Total retrieval: `{"max": 61476.227, "mean": 21194.238, "min": 1858.44, "p50": 2103.937, "p95": 60933.124}`

## Isolation and acceptance

- Namespace unchanged: `true`
- SRS comparison: `{"final_answer_abstention": "NOT_EVALUATED", "grounding_citation_generation": "NOT_EVALUATED", "leakage_adversarial": "NOT_EVALUATED", "meaningful_improvement": "NOT_EVALUABLE_INCOMPLETE_PROVIDER_SUCCESS", "nfr_perf_006_provider_http_p95": "PASS", "nfr_rag_006_hit_at_5": "NOT_EVALUABLE", "nfr_rag_006_mrr_at_10": "NOT_EVALUABLE", "provider_reliability": "FAIL"}`
- Generation, citation, final-answer abstention and adversarial leakage were not evaluated.

Per-case candidate fingerprints, ranks and provider timing are in the JSON artifact.
