# RAG-05 Isolated Staging Qdrant Retrieval Evaluation

- Executed at: `2026-09-05T19:39:13.372196+00:00`
- Dataset: `rag05-raw-wiki-golden-v1-draft`
- Approved content fingerprint: `01cababd2e9912a1b435869afc500dc44d727d045f6bafe868c3be4bc6004976`
- Corpus version: `raw-wiki-sha256:0efe04a586291c11c84c921a1839ac20be53f12c026e3ea2b43595e9a7d32c7a`
- Production equivalent: `true`
- Qdrant endpoint: `http://localhost:16333`
- Collections: `{"character_lore": "character_lore__rag05eval_01cababd2e_20260905192227", "story_lore": "story_lore__rag05eval_01cababd2e_20260905192227", "world_lore": "world_lore__rag05eval_01cababd2e_20260905192227"}`

## Answerable-slice quality

- Cases: `81`
- Hit@1: `0.679012`
- Hit@3: `0.901235`
- Hit@5: `0.950617`
- MRR@10: `0.788889`
- First-stage misses: `4`
- Context precision: `not_evaluable_label_incomplete`
- Abstention evaluation: `not_evaluable_at_retrieval_stage`

## Offline comparison

- Identical top-k: `0/83`
- Ranking changes: `29`
- Newly missed: `4`
- Recovered: `0`
- Material semantic differences: Qdrant named dense/BM25 search, public ACL filter, configured score threshold/candidate budgets, production parent hydration, and production cross-collection fusion are exercised only by this staging run.

## Safety and parity

- Alias namespace unchanged: `true`
- Unexpected collection changes: `[]`
- Parent hydration mismatches: `0`
- Retrieval modes: `{"hybrid_rrf": 415}`
- Remote reranker: disabled; no provider request was made.
- Active corpus/index aliases were not created, changed, or deleted.

Per-case evidence and candidate differences are recorded in the JSON artifact.