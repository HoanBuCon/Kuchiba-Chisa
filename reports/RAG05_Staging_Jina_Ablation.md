# RAG-05 Production-Equivalent Staging Jina Ablation

- Executed at: `2026-09-05T21:18:58.764953+00:00`
- Dataset fingerprint: `01cababd2e9912a1b435869afc500dc44d727d045f6bafe868c3be4bc6004976`
- Corpus version: `raw-wiki-sha256:0efe04a586291c11c84c921a1839ac20be53f12c026e3ea2b43595e9a7d32c7a`
- Staging version: `rag05eval_01cababd2e_20260905192227`
- Production-equivalent first-stage/candidate path: `true`; live remote reranker: `true`; end-to-end generation: `false`
- Effective benchmark pacing: `{"limit_source": "Jina documented free-key limits, verified at preflight", "requests_per_minute": 100, "rolling_window_safety_margin_ms": 250, "tokens_per_minute": 100000}`

## Quality

- Baseline: `{"context_precision": "not_evaluable_label_incomplete", "hit_at_1": 0.679012, "hit_at_3": 0.901235, "hit_at_5": 0.950617, "mrr_at_10": 0.79249}`
- Jina: `{"context_precision": "not_evaluable_label_incomplete", "hit_at_1": 0.851852, "hit_at_3": 0.975309, "hit_at_5": 0.975309, "mrr_at_10": 0.909465}`
- Improved/unchanged/degraded: `20` / `58` / `3`
- First-stage misses: `['rw-013', 'rw-035', 'rw-041', 'rw-060']`
- Recovered into top-k: `['rw-013', 'rw-041']`
- Unrecoverable candidate misses: `['rw-035', 'rw-060']`
- Context precision: `not_evaluable_label_incomplete`
- Abstention: `not_evaluable_at_retrieval_stage`

## Provider and latency

- Telemetry: `{"calls": 83, "cost_semantics": "not_evaluable_public_unit_price_unavailable", "estimated_cost_usd": null, "failure_counts": {"invalid_response": 0, "provider": 0, "rate_limit": 0, "timeout": 0, "unavailable": 0}, "fallback_count": 0, "privacy_policy_rejection_count": 0, "processed_token_estimate": 200337, "reserved_token_estimate": 200337, "validated_responses": 83}`
- Provider HTTP: `{"max": 580.983, "mean": 360.327, "min": 310.211, "p50": 352.587, "p95": 413.085}`
- Pacing: `{"mean": 1095.084, "p50": 0.0, "p95": 0.0, "paced_cases": 3, "total": 90891.986}`
- Reranker total: `{"max": 46095.361, "mean": 1456.814, "min": 311.079, "p50": 354.225, "p95": 499.046}`
- Total retrieval: `{"max": 47713.658, "mean": 3109.494, "min": 1912.925, "p50": 1965.105, "p95": 2196.93}`

## Isolation and acceptance

- Namespace unchanged: `true`
- SRS comparison: `{"final_answer_abstention": "NOT_EVALUATED", "grounding_citation_generation": "NOT_EVALUATED", "leakage_adversarial": "NOT_EVALUATED", "meaningful_improvement": "OBSERVED_GAIN", "nfr_perf_006_provider_http_p95": "PASS", "nfr_rag_006_hit_at_5": "PASS", "nfr_rag_006_mrr_at_10": "PASS", "provider_reliability": "PASS"}`
- Generation, citation, final-answer abstention and adversarial leakage were not evaluated.
- Provider recommendation: `{"classification": "NEEDS_MORE_EVIDENCE", "production_default_changed": false, "reason": "ranking, latency, and reliability passed; actual provider cost, generation grounding/citations, final-answer abstention, and adversarial leakage remain unevaluated"}`

## Voyage comparison

- The completed Voyage offline raw_wiki run is not production-equivalent and therefore is not an apples-to-apples quality comparison.
- The production-equivalent Voyage staging attempt used the same candidate path but completed only 68/83 validated responses, with 15 HTTP 429 responses and 15 fallbacks. Its full Hit@K/MRR result is not evaluable.
- Valid-response HTTP latency samples are methodologically useful but not a complete provider decision: Voyage staging p95 was 446.094 ms; Jina full staging p95 was 413.085 ms.
- No production provider default was changed.

Per-case candidate fingerprints, ranks and provider timing are in the JSON artifact.
