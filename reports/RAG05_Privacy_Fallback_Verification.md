# RAG-05 Remote Provider Privacy and Fallback Verification

| Field | Value |
|---|---|
| Scope | Focused RAG-05 remote reranker boundary only |
| Requirement trace | `RAG-05`, `FR-RAG-005`, `SEC-DATA-002`, `NFR-OPS-002`; focused evidence toward `SEC-RAG-008` only |
| Provider contract exercised | Jina-compatible `ApiCrossEncoderReranker`; mocks restricted to deterministic failure paths |
| Production retrieval boundary | `LoreRetriever._cross_encoder_rerank` |
| Result | **PASS** |
| Full SAFE-01/SAFE-02 | **OPEN / NOT CLAIMED** |
| RAG-06 grounding/citations | **OUT OF SCOPE / NOT CLAIMED** |

## Provider-boundary behavior

- Remote reranking is allowed only when every rerankable evidence candidate has `access_scope=public`.
- A user-private, tenant-private, or mixed public/private candidate set causes zero remote calls and uses the deterministic local fallback with reason `remote_policy`.
- Only the retrieval query and public candidate `text_content` are serialized. Candidate metadata fields are not included in the provider body.
- The API adapter applies irreversible high-confidence PII/secret redaction to both query and candidate documents before the HTTP boundary.
- Public/approved lore containing prompt-injection-like prose is treated as inert evidence text. It may be scored remotely, but it receives no control channel and cannot introduce system/persona/relationship prompt fields into the request schema.

## Focused adversarial cases

| Case | Remote call | Expected result | Verified telemetry |
|---|---:|---|---|
| Public lore with injection-like text and PII/secret-shaped values | 1 boundary capture followed by simulated network failure | Only minimized, redacted query/documents cross boundary; then local fallback | `lexical_fallback`, `provider_unavailable` |
| User-private memory evidence | 0 | Local deterministic order | `lexical_fallback`, `remote_policy`, degraded `true` |
| Tenant-private evidence | 0 | Local deterministic order | `lexical_fallback`, `remote_policy`, degraded `true` |
| Mixed public and private candidates | 0 | Entire rerank batch remains local | `lexical_fallback`, `remote_policy`, degraded `true` |
| Provider HTTP 429 | 1 | Provider result rejected; local deterministic order | `provider_rate_limit` |
| Provider timeout | 1 | Provider result unavailable; local deterministic order | `provider_timeout` |
| Invalid provider response | 1 | Invalid score not used; local deterministic order | `provider_invalid_response` |
| Provider network unavailable | 1 | Provider result unavailable; local deterministic order | `provider_unavailable` |

Each simulated provider failure makes exactly one request. No retry loop or retry storm was introduced. Mocks are used only to create deterministic outbound capture and failure conditions; successful production-provider evidence remains the genuine 83/83 Jina staging artifact, not a mocked response.

## Payload assertions

The captured allowed remote payload was restricted to:

- `model`
- `query`
- `documents`
- `top_n`
- `return_documents`

The focused suite verifies absence of raw email addresses, secret-shaped values, private-memory text, tenant-private text, system-prompt metadata, persona-prompt metadata, relationship-prompt metadata, internal-secret metadata, and provider credentials from the serialized request body. Authorization remains an HTTP header concern and is not copied into the payload.

## Leakage evidence

These counts apply only to the focused RAG-05 remote reranker boundary suite:

| Leakage class | Observed |
|---|---:|
| Cross-tenant evidence sent remotely | 0 |
| Raw PII sent remotely | 0 |
| Protected prompt metadata sent remotely | 0 |
| Private/user evidence sent remotely | 0 |

This evidence does not establish full application jailbreak resistance, broad PII entity classification, consent/DPA compliance, log-store privacy, final-answer grounding, or citation correctness. Those remain owned by SAFE-01, SAFE-02 and RAG-06.

## Verification

- Focused provider-boundary/fallback suite added by this goal: 8 passed.
- Changed-lines Ruff gate: passed.
- Mypy application gate: 272 source files passed.
- `pip check`: no broken requirements.
- Full-file Ruff audit still reports nine pre-existing legacy findings in `retriever_lore.py`; none intersects this batch's changed lines and no suppression/bulk fix was added.
- The focused privacy/fallback suite made no external provider call and does not
  count provider smoke traffic as privacy evidence. A separate, user-authorized
  one-document Jina pacing/quota smoke returned HTTP 200 after this verification;
  it did not run retrieval, use private data, or alter this report's evidence.
- No golden-set change, corpus/index mutation, provider-default change,
  SRS-threshold change, or protected-prompt change occurred.

## Acceptance interpretation

The focused RAG-05 remote provider boundary and deterministic fallback evidence is **PASS**. Overall RAG-05 remains OPEN for any acceptance evidence not covered here. SAFE-01, SAFE-02 and RAG-06 remain explicitly OPEN.
