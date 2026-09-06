# RAG-06 Grounding Remediation Verification

Recorded: 2026-09-06T18:13:00+07:00  
Status: **OPEN / HUMAN REVIEW REQUIRED**  
Trace: `RAG-06`, `TD-038`, `FR-RAG-008`, `FR-RAG-009`, `SEC-RAG-006`, `SEC-RAG-007`, `NFR-RAG-001`, `NFR-RAG-002`, `NFR-RAG-005`, `NFR-RAG-007`

## Implementation

- Evidence-backed DeepSeek calls use a forced function/tool contract carrying the dynamic JSON Schema. DeepSeek JSON mode alone did not receive or enforce the project's schema.
- The model proposes atomic claims, selected evidence IDs and short supporting quotes. Server validation rejects undeclared IDs and fields.
- Citation mapping is server-owned. A claimed citation may be rebound only when its quote resolves deterministically within another server-selected evidence item.
- Exact MediaWiki display normalization handles link markup without fuzzy semantic substitution. A high-threshold sentence match may resolve minor copy differences, but the delivered fallback sentence always comes from selected evidence.
- Every claim is scored against its resolved supporting sentence rather than the whole chunk. Unsupported paraphrases are removed from delivery and replaced with the resolved extractive sentence.
- Grounded output that fails quote, leakage or claim checks returns a server-owned abstention rather than leaking a candidate or returning false success.
- Answer and abstain are separate typed decisions. Abstention has no claims or citations.
- Grounded function calls disable DeepSeek thinking for that call because the provider rejects forced `tool_choice` with thinking enabled. Other runtime defaults are unchanged.
- Retrieved evidence sequences are excluded from prompt-leak detection only as approved output sources; protected instruction sequences remain blocking.
- Attachment IDs remain server-owned and are never sourced from model output.

Protected system/persona/relationship prompt content was not modified.

## Frozen v2 evaluation artifact

- Artifact: `data/evaluations/drafts/rag06_final_answer_review_v2.{json,md,validation.json}`
- Previous v1 artifact: retained unchanged as pre-remediation evidence.
- Golden-set fingerprint: unchanged.
- Retrieval/Jina configuration: unchanged.
- Corpus/index mutations: 0.
- Cases: 38 total; 36 answerable and 2 approved abstentions.
- Genuine provider responses captured: 38/38.
- Safe delivery: 38/38.
- Evidence-backed answers with server-validated citations: 34.
- Server abstentions: 4.
- Both approved abstention cases returned `abstained_insufficient_evidence` with zero citations.
- One answerable candidate was converted to `abstained_output_leakage`; one answerable candidate chose `abstained_insufficient_evidence`.
- Semantic auto-scores: 0.
- Human reviews pending: 38.

These counts are structural evidence only. They do not establish faithfulness, answer relevance, citation correctness or abstention precision.

## Verification

- Focused RAG-06/security/provider tests: 49 passed.
- `mypy app`: PASS, 274 files.
- Changed-lines Ruff: PASS.
- Provider smoke: real `deepseek-v4-flash` function response validated; no secret or response content logged by the smoke result.
- Structural validator: PASS.

## Remaining acceptance boundary

Human semantic review must resolve all pending cases and compute the SRS metrics. Any unsupported non-abstaining result on an approved no-answer case remains blocking. `RAG-06` and `TD-038` must not be closed until the reviewed results satisfy every threshold.

