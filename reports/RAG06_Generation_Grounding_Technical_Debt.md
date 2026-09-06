# RAG-06 Generation/Grounding Remediation Debt

Recorded: 2026-09-06T16:40:21+07:00  
Status: **OPEN / HUMAN REVIEW REQUIRED**  
Debt ID: `TD-038`

## Scope and traceability

This debt tracks `RAG-06`, `FR-RAG-008`, `FR-RAG-009`, `SEC-RAG-007`, `NFR-RAG-001`, `NFR-RAG-002`, `NFR-RAG-005`, and `NFR-RAG-007`.

Evidence:

- `data/evaluations/drafts/rag06_final_answer_review_v1.{json,md,validation.json}`
- `reports/RAG06_Human_Review_Batch_01.md`

## Findings

- Current RAG-06 review sample has a generation-quality failure.
- Required citations are not emitted, so citation compliance fails and claim-to-evidence binding is absent.
- Candidate answers contain unsupported factual/persona embellishment and causal-attribution errors.
- One case encountered token overflow.
- Service utility fails for the reviewed run because generated candidates are rejected at the delivery boundary instead of producing useful schema-valid answers.
- Batch 01 human feedback classified 1/10 cases as supported, 7/10 as partially supported, 2/10 as unsupported, and 3/10 as containing a critical unsupported claim.

#### Preserved safety evidence

- Delivery fail-closed behavior worked: rejected candidates were not delivered to users.
- First-stage retrieval and Jina reranking are not identified as the root cause by this evidence.
- Protected system/persona/relationship prompts remain unchanged.
- Missing citations are recorded as citation-compliance failure. Citation correctness over emitted citation links is not fabricated when no links exist.

## Closure conditions

`TD-038` and `RAG-06` remain open until all of the following are demonstrated on a frozen, versioned final-answer evaluation with human audit:

- Faithfulness/groundedness ≥ 0.90 overall and zero critical unsupported claims.
- Answer relevance ≥ 0.85.
- Citation correctness ≥ 0.95 with required citation emission and auditable claim-to-evidence binding.
- Abstention precision ≥ 0.90, with every unsupported non-abstaining answer treated as blocking.
- Token budgets prevent overflow or cause an explicit safe abstention/error outcome.
- Schema-valid grounded answers reach the delivery boundary successfully.
- Security, privacy, tenant isolation, and protected-prompt constraints remain intact.

Remediation is explicitly outside the scope of the goal that recorded this debt.

## Remediation update — 2026-09-06

The approved code-bound remediation is implemented and recorded in
`reports/RAG06_Grounding_Remediation_Verification.md`. Frozen v2 structural
evaluation passed with 38/38 provider responses and safe deliveries, while
semantic review remains pending for every case. This update does not close
`TD-038` or infer that any semantic threshold passed.
