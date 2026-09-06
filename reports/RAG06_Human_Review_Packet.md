# RAG-06 Human Review Packet

Status: **REVIEW REQUIRED — evaluation not executed**  
Prepared: 2026-09-06 (Asia/Saigon)  
Requirements: `RAG-06`, `FR-RAG-008`, `FR-RAG-009`, `FR-RAG-011`, `NFR-RAG-001`, `NFR-RAG-002`, `NFR-RAG-005`, `NFR-RAG-007`

## 1. Decision requested from the project owner

Approve or reject the evaluation protocol in this document. Approval authorizes creation of a versioned **final-answer** evaluation artifact using the current application generation path and the current protected prompts unchanged. It does not approve any generated answer in advance and does not waive an SRS threshold.

No final-answer artifact currently exists, so semantic scores cannot honestly be assigned yet.

## 2. Frozen inputs

| Item | Frozen value |
|---|---|
| Golden set | `data/evaluations/approvals/rag05_raw_wiki_golden_v1.json` |
| Approval state | Human-approved |
| Approved content SHA-256 | `01cababd2e9912a1b435869afc500dc44d727d045f6bafe868c3be4bc6004976` |
| Cases | 83 total: 81 answerable, 2 abstention |
| Retrieval evidence | Production-equivalent first-stage Qdrant dense+sparse/RRF and Jina reranking artifacts already accepted |
| Context relevance | 405/405 retrieved top-5 items human-labelled relevant; context precision 1.0 |
| Generation path | Current application generation/output-validation path; no benchmark-only prompt |
| Protected content | System/persona/relationship prompts must remain byte-for-byte unchanged |

The 405 relevance decisions validate retrieval context precision only. They do not establish that a generated answer is faithful, relevant, correctly cited, or appropriately abstains.

## 3. Existing implementation evidence

The current implementation already has deterministic controls for:

- rejecting citation IDs outside server-selected evidence;
- rejecting citations when no evidence was selected;
- abstaining without calling the LLM when factual evidence is absent;
- rejecting unsupported factual claims even when a citation ID is valid;
- rejecting numeric claims whose number does not occur in cited evidence;
- withholding invalid streamed output before any token reaches the sink.

Focused evidence: `tests/unit/security/test_grounding_citations.py` — 8/8 passed in the latest focused P1 run. This proves guard behavior, not corpus-level semantic performance.

## 4. Proposed evaluation protocol

### 4.1 Execution

For each frozen case, record:

1. case ID and query;
2. expected behavior (`answer` or `abstain`);
3. exact selected evidence IDs and source excerpts;
4. validated model answer exactly as delivered after output guards;
5. returned citation IDs;
6. whether generation was rejected, safely abstained, or delivered;
7. provider/model/config version and latency, without prompts, secrets, PII, or hidden reasoning;
8. immutable fingerprints for dataset, corpus, selected evidence and evaluation artifact.

No query, expected answer, evidence label, retrieval parameter, reranker parameter, or prompt may be changed after outputs are observed.

### 4.2 Human labels

Every answerable case receives the following reviewer fields:

| Field | Allowed values | Review rule |
|---|---|---|
| `critical_unsupported_claim` | `yes`, `no` | `yes` if any material factual claim contradicts or lacks support from the cited evidence. |
| `faithfulness` | `supported`, `partially_supported`, `unsupported` | Judge claim support only from displayed evidence, not model memory or external game knowledge. |
| `answer_relevance` | `relevant`, `partially_relevant`, `irrelevant` | Judge whether the answer directly resolves the user query without material diversion. |
| `citation_correctness` | `correct`, `partially_correct`, `incorrect` | A citation is correct only when that exact evidence materially supports the associated claim. |
| `raw_data_quality_issue` | `none`, `markup_noise`, `boundary_noise`, `insufficient_source`, `other` | Track corpus defects separately; do not relabel a hallucination as a corpus issue. |
| `reviewer_comment` | free text | Required for every partial/failed label. |

Each abstention case receives:

| Field | Allowed values | Review rule |
|---|---|---|
| `abstained` | `yes`, `no` | The delivered response explicitly states insufficient grounded information or asks for clarification. |
| `unsafe_guess` | `yes`, `no` | `yes` if the response supplies unsupported factual content instead of abstaining. |
| `abstention_appropriate` | `yes`, `no`, `ambiguous` | Judge against the approved no-answer label and displayed search result. |

### 4.3 Metric semantics

| Requirement | Proposed computation | SRS threshold |
|---|---|---|
| `NFR-RAG-001` faithfulness | Fully supported factual claims / all reviewed factual claims; any critical unsupported claim is separately blocking. | ≥ 0.90 and zero critical unsupported claim |
| `NFR-RAG-002` answer relevance | Cases labelled relevant / evaluated answerable cases. Partial labels are reported separately and not silently counted as relevant. | ≥ 0.85 |
| `NFR-RAG-005` citation correctness | Correct claim–citation links / all reviewed claim–citation links. Missing required citations count as incorrect. | ≥ 0.95 |
| `NFR-RAG-007` abstention precision | Appropriate abstentions / all responses that abstained within the approved no-answer slice. Non-abstaining unsafe guesses are reported separately. | ≥ 0.90 |

The final artifact must report evaluator version, sample size, point estimate, confidence interval and reviewer provenance. Pending or ambiguous labels must keep the corresponding metric `NOT EVALUABLE`; they must not be converted to failures or successes.

## 5. Known review limitation

The approved dataset contains only two abstention cases. A 2/2 result has a point estimate of 1.0 but very wide statistical uncertainty. The protocol will report that limitation and its confidence interval; it will not claim strong corpus-wide abstention assurance from two examples. The current closure directive prohibits expanding the golden set, so this limitation cannot be hidden by manufacturing additional cases.

## 6. Raw-wiki quality note

The reviewer confirmed that all 405 retrieved items materially answer their queries, while some excerpts contain raw MediaWiki syntax, table residue or broken boundaries such as:

- a chunk beginning mid-word (`ity.`);
- `[[Leviathan]]` / `[[Imperator]]` link markup;
- `==Archive Entry==` section markup;
- table records merged with unrelated surrounding prose.

These are ingestion/chunking quality findings. During RAG-06 review, they must be recorded in `raw_data_quality_issue`; they must not be used to excuse an unsupported generated claim or an incorrect citation.

## 7. Approval record

Reviewer decision: **PENDING**  
Reviewer identity: **PENDING**  
Review timestamp: **PENDING**  
Reviewer notes: **PENDING**

Suggested explicit decision:

> I approve RAG-06 Human Review Protocol v1 and authorize generation of the versioned 83-case review artifact using the current production-equivalent retrieval/generation path, with protected prompts unchanged. This approval does not pre-approve outputs or waive SRS thresholds.

## 8. Current acceptance state

`RAG-06: BLOCKED — awaiting protocol approval and subsequent human review of real generated outputs.`

`P1 FORMAL CLOSURE: NO-GO`
