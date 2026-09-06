# RAG-06 Final Acceptance Evidence

Date: 2026-09-06 (Asia/Saigon)  
Reviewer: `HoanBuCon` (project owner)  
Evaluator: `rag06-human-review-v1`  
Frozen artifact: `data/evaluations/drafts/rag06_final_answer_review_v2.*`

## Decision

`RAG-06: PASS`

The project owner explicitly reviewed and approved the complete frozen 38-case
RAG-06 v2 sample. Approval changes only human-review and acceptance metadata.
The frozen sample, generated outputs, evidence/citation mapping, approved golden
set fingerprint, retrieval/Jina configuration, corpus/index state and protected
prompt content remain unchanged.

## Provenance and integrity

- Golden-set content SHA-256: `01cababd2e9912a1b435869afc500dc44d727d045f6bafe868c3be4bc6004976`
- Frozen RAG-06 content SHA-256 before review metadata:
  `333005f855fcb848a9daee35ef29ae4309669b6ebe43f1dec291172928e11ebd`
- Frozen RAG-06 content SHA-256 after review metadata:
  `333005f855fcb848a9daee35ef29ae4309669b6ebe43f1dec291172928e11ebd`
- Staging version: `rag05eval_01cababd2e_20260905192227`
- Provider/model: `deepseek` / `deepseek-v4-flash`
- Sample: 38 cases: 36 answerable and both approved no-answer cases.
- Selection: deterministic SHA-256 ordering across language/category/difficulty
  strata, with every approved no-answer case included.
- Human review recorded at `2026-09-06T18:39:10.6572003+07:00`.
- Review state: 38 approved, 0 pending; semantic auto-scores: 0.

Confidence intervals use the existing two-sided Wilson 95% method. SRS gates
compare the point estimate to the stated threshold; intervals are retained to
show sample uncertainty and are not hidden or converted into new thresholds.

## Metrics and SRS comparison

| Requirement | Human-reviewed result | Wilson 95% CI | Threshold | Status |
|---|---:|---:|---:|---|
| `NFR-RAG-001` faithfulness | 44/44 material claims = **1.000000** | [0.919704, 1.000000] | >= 0.90 | PASS |
| `NFR-RAG-001` critical unsupported claims | **0** | N/A | 0 | PASS |
| `NFR-RAG-002` answer relevance | 31/36 relevant = **0.861111** | [0.713405, 0.939182] | >= 0.85 | PASS |
| `NFR-RAG-005` citation correctness | 64/64 material claim-citation links = **1.000000** | [0.943376, 1.000000] | >= 0.95 | PASS |
| `NFR-RAG-007` abstention precision | 2/2 appropriate abstentions in the approved no-answer slice = **1.000000** | [0.342380, 1.000000] | >= 0.90 | PASS |

The relevance numerator intentionally excludes the three human-approved partial
cases (`rw-037`, `rw-060`, `rw-066`). They are not silently counted as fully
relevant.

## Findings retained without concealment

- `rw-003` is a false insufficient-evidence abstention on an answerable case.
- `rw-044` is a safe leakage-guard abstention on an answerable case; the expected
  answer was not delivered.
- Those two cases are counted as irrelevant in the 36-case answerable relevance
  denominator. They are not inserted into the approved no-answer abstention-
  precision denominator.
- The two approved no-answer cases both abstained and produced zero unsafe
  guesses. The 2/2 point result has a very wide Wilson interval and is not strong
  corpus-wide assurance.
- Raw MediaWiki markup, broken excerpt boundaries and over-extractive phrasing
  remain ingestion/readability debt. Human semantic approval does not assert
  that the raw corpus is presentation-clean.

## Structural and safety evidence

- 38/38 provider responses were captured and 38/38 paths produced safe delivery.
- 34 answerable cases produced server-bound cited answers; four responses
  abstained.
- Typed claim/evidence output, strict schema validation, deterministic evidence
  quote resolution, server-owned citations and fail-closed output handling remain
  covered by focused regression tests.
- Streaming unsupported claims remain blocked by the same grounding boundary as
  non-streaming output.
- Protected system/persona/relationship prompt checksums match the frozen
  artifact provenance.

## Technical debt retained

The formal RAG-06 thresholds pass, so the following non-blocking findings remain
tracked rather than being hidden or used to rewrite the frozen evaluation:

1. Reduce false abstention behavior represented by `rw-003` and `rw-044` without
   weakening fail-closed grounding/leakage policy.
2. Improve canonical ingestion cleanup/chunk boundaries for raw-wikitext markup
   and readability under `ING-01`.
3. Expand approved no-answer coverage in a future versioned evaluation task; do
   not overstate assurance from two cases.

`TD-038` is resolved by the reviewed v2 evidence. No SRS threshold was waived.
