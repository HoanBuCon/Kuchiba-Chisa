# ING-02 Isolated Publish and Rollback Verification

Status: **PASS**
Requirement: `FR-ING-007`, `FR-ING-008`, `ING-02`

## Isolation boundary

- Docker Compose project: `kuchiba-chisa-ing02`.
- PostgreSQL endpoint: `localhost:55432/chisa_test`.
- Qdrant endpoint: `localhost:16333`.
- Existing production-like containers on ports 5432/6333 were not used or mutated.
- Disposable containers, network, and volumes were removed after evidence capture.

## Verified transaction

1. Migrated a fresh isolated PostgreSQL database to Alembic head.
2. Created retained prior and candidate physical Qdrant collections with dense and BM25 vectors.
3. Persisted versioned PostgreSQL parents, source provenance, release receipts, and manifests.
4. Published the quality-passed candidate through the lifecycle service.
5. Confirmed `character_lore__active` atomically targeted the candidate.
6. Rolled the release back through the same lifecycle service.
7. Confirmed the alias atomically returned to the retained prior collection.
8. Confirmed both physical collections remained retained and the candidate release became `rolled_back`.

## Durable receipt

- Candidate: `character_lore__ing02candidate_0f449404a6`.
- Retained prior: `character_lore__ing02prior_0f449404a6`.
- Final alias target: retained prior.
- Candidate final PostgreSQL status: `rolled_back`.
- Candidate audit actions: `quality_passed`, `promotion_requested`, `published`, `rollback_requested`, `rolled_back`.
- Integration result: 1 passed, 0 failed.

The test uses a random suffix on every execution; identifiers above document this specific verification receipt only.
