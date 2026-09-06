# ING-01 Canonical Ingestion Parity Blocker

Status: **RESOLVED / SUPERSEDED 2026-09-06**
Requirement: `ING-01`, `TD-030`

The exit conditions below are retained as the historical blocker record. They
were satisfied by the implementation and evidence in
`reports/ING01_Canonical_Parity_Verification.md`; this file is no longer the
current ING-01 status.

## Verified current state

- `run-dag` is the canonical application ingestion entry point and executes the versioned staged DAG.
- `run-pipeline` still imports and executes `MasterIngestionPipeline`.
- Legacy commands for crawl, canonical build, chunk processing, SQLite/Qdrant sync, orphan cleanup, quality validation, enrichment, and benchmark remain executable.
- Existing tests explicitly require legacy commands and their file-based/SQLite behavior.
- Canonical and legacy implementations use different parser/chunking/storage semantics; the observed raw-wikitext evaluation noise is evidence that their outputs must not be assumed equivalent.

## Why retirement did not proceed

The SRS permits legacy retirement only after parity is proven. Current evidence proves ordered canonical DAG behavior and fail-closed staging, but does not prove fixture-level output/state parity or complete call-site migration. Removing or redirecting the legacy path now could change data semantics and would violate `ING-01`.

## Exit conditions

1. Define a reviewed parity fixture covering source revision, canonical text, chunk identity/span, ACL/provenance, incremental behavior, parent persistence, dense+sparse vector receipt, and failure acknowledgement.
2. Run both paths against the fixture without active-index mutation and record all intentional semantic differences.
3. Migrate remaining CLI/scripts/tests/operators to `run-dag` or an explicitly retained non-ingestion operational command.
4. Remove or make the legacy executable path non-runnable only after the parity receipt passes.

Completing these conditions requires a dedicated ingestion migration task; it was not hidden behind deprecation wording or a command alias in this goal.
