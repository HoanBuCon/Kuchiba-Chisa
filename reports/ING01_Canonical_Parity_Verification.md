# ING-01 Canonical Ingestion Parity and Migration Verification

Date: 2026-09-06 (Asia/Saigon)
Requirement: `ING-01`, `TD-030`, with supporting `FR-ING-002`, `FR-ING-003`,
`FR-ING-005`, `FR-ING-006`, `FR-ING-007`, `FR-ING-008`

## Decision

`ING-01: PASS`

The application-level `IngestionOrchestrator` and `run-dag` command are now the
only executable standard corpus-ingestion path. Legacy file/SQLite/direct-Qdrant
composition was retired only after a deterministic fixture comparison and after
the canonical path's persistence, vector receipt, failure acknowledgement and
release lifecycle evidence had passed.

## Reviewed parity fixture

The versioned fixture in
`tests/unit/ingestion/test_ing01_canonical_parity.py` contains one real-shaped
MediaWiki page contract:

- page ID `585`, revision `101912`, title `Aalto`;
- three explicit factual statements across lead, background and relationship
  sections;
- source UUID `c7ad47e2-41a1-5a88-8a88-bc3c0b9c0638`;
- corpus version `v20260906` and public ACL.

The comparison runs the former canonical builder/chunker components and the
application Parser → ParentBuilder → SemanticChunkBuilder stages in memory. It
proves that both representations retain the same three source facts and the same
page/revision identity. It also proves the selected application path produces:

- deterministic parent and chunk UUIDs on identical input;
- content-derived chunk hashes;
- exact child offsets resolvable into parent Markdown;
- source UUID, corpus version and ACL propagation to parents/chunks;
- changed revision/content producing new identities (covered by the existing
  `test_deterministic_ingestion_ids.py` suite).

## Intentional representation differences

These differences were reviewed rather than hidden:

| Area | Retired composition | Canonical application DAG | Disposition |
|---|---|---|---|
| Text representation | `CanonicalPage`/`Chunk`, including normalized Markdown emphasis | `ParsedPage` → `LoreParent` → `ProcessingChunk` | Factual text parity is compared after Markdown presentation normalization; source revision remains authoritative. |
| Identity | Page/heading-oriented legacy IDs | Content/revision/offset-aware deterministic parent and chunk IDs | Canonical identity selected because it satisfies `FR-ING-005` audit/version semantics. |
| ACL/provenance | File/SQLite path did not carry the complete release contract | Typed source, corpus version, ACL and offsets through parent/vector payload | Canonical contract selected; no permissive compatibility shim retained. |
| Incremental state | Local SQLite page/chunk state | PostgreSQL sync/chunk state plus immutable corpus version | Canonical state owner selected; full candidate builds do not reuse the SQLite path. |
| Publication | Direct scripts could delete/write active logical collections | DAG accepts only a physical versioned staging collection; ING-02 separately owns alias publish/rollback | Unsafe direct mutation path removed. |

The raw-wikitext markup/boundary/readability finding remains quality debt; parity
does not claim that source text is presentation-clean or that two representations
are byte-identical.

## State and side-effect parity evidence

- `test_ingestion_orchestrator.py` proves ordered execution, source/version/ACL
  propagation, parent persistence only after vector acknowledgement, durable job
  failure state and staged release/audit receipt.
- `test_qdrant_upsert_stage.py` and ING-02 integration evidence prove dense+sparse
  named-vector acknowledgement to a physical staging collection.
- `test_ing02_publish_rollback.py` proves quality-gated publish and rollback while
  retaining both physical collections.
- Corpus poisoning is now checked in canonical `ValidationStage` before the
  embedding stage; `QdrantUpsertStage` retains the same gate as defense in depth.
- Active aliases are rejected by `IngestionRunRequest`; the composition root does
  not create, delete or promote collections.
- `AllPagesSyncStrategy` enumerates every approved source page for a new physical
  corpus version. Stored revision state remains an audit/download receipt and
  cannot accidentally turn a full-version build into an incomplete delta-only
  collection.

## Call-site migration and retirement

- `app.infrastructure.ingestion.cli` exposes only `run-dag`.
- `chisa_cli.py ingest` requires an approved source UUID and physical versioned
  staging collection, then invokes the same canonical composition function.
- Old `scan`, `crawl`, `clean`, `benchmark` ingestion modes fail closed with a
  migration message.
- `MasterIngestionPipeline` and its executable module were removed.
- Direct destructive/file-based scripts for production ingest, re-ingest,
  incremental ingest, parent resync and ingestion-data clearing were removed.
- Low-level parser/chunker models remain as non-entry-point implementation and
  test utilities where still useful; retaining a component does not retain the
  retired orchestration path.

Repository search finds no remaining executable/import call site for
`MasterIngestionPipeline`, `app.infrastructure.ingestion.pipeline` or
`run-pipeline` outside negative regression assertions and historical reports.

## Safety and limitations

No active collection, alias, corpus row or production index was mutated for this
verification. No legacy command was redirected into an operation with different
semantics; unsupported modes now fail explicitly. No protected
system/persona/relationship prompt was modified.

## Verification

- Focused canonical ingestion suite: 134 passed, 1 service-backed benchmark
  deselected; the separately executed benchmark passed against isolated Qdrant.
- ING-01 focused regression batch: 21 passed.
- Real isolated Qdrant benchmark plus PostgreSQL/Qdrant publish/rollback: 2 passed.
- Full repository suite with isolated PostgreSQL, Redis and Qdrant: 567 passed.
- Mypy: 274 source files passed.
- Changed-lines Ruff: PASS.
- Linux Docker test image: built successfully; container smoke 12 passed and
  `pip check` reported no broken requirements.
