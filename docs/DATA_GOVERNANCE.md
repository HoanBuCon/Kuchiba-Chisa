# Data governance and retention

This inventory implements the classification and policy boundary required by
`SEC-DATA-001`, `SEC-DATA-002`, `SEC-DATA-008`, `FR-CTX-003`, and `SAFE-02`.
It describes the deployed code contract; it is not a substitute for a
market-specific legal retention schedule.

| Data class | Purpose / owner | Active storage | Runtime control |
|---|---|---|---|
| Verified principal identifier | Authentication, ownership, isolation / Security | JWT claims, PostgreSQL user key, scoped cache key | Never derive it from request payload; telemetry uses a hash. |
| Conversation and emotion state | Session continuity / Product | PostgreSQL and tenant-scoped Redis cache | Erasure workflow removes active user data. Raw content is excluded from default telemetry. |
| Derived long-term text, image, and community memory | User-requested continuity / Product | Qdrant memory collections | Default deny. A verified principal enables it at `PUT /api/v1/chat/me/memory-consent` with a 1–365 day retention period. Revocation deletes that principal's active text, image, and contributor-owned community vectors; read paths reject records after `expires_at`. |
| Image original and derived caption | Vision request / Product | Approved image storage and Qdrant image memory | Ephemeral image references are never persisted. Long-term image indexing requires the same explicit memory consent and carries `expires_at`. |
| Guild/channel content | Community interaction / Guild policy owner | Tenant-scoped PostgreSQL, Redis, and Qdrant | Adapter-derived tenant/channel identity and authorization are mandatory. Derived community state is not created without the acting principal's consent. |
| Retrieval documents and embeddings | Grounded answer / Content curator | Versioned Qdrant and PostgreSQL parent store | Source provenance, ACL, corpus version, and collection route are required. Retrieval enforces ACL before ranking and hydration. |
| Operational log, trace, and metric data | Reliability and incident response / SRE | Structured logs and Redis trace store | Metadata-only by default; no prompt/history/evidence/raw output. Pipeline trace TTL is `PIPELINE_TRACE_TTL_SECONDS`. |

## Provider minimization

Immediately before an LLM provider call, `ProviderPiiRedactionStage` creates a
redacted copy of the structured prompt. It masks high-confidence email, phone,
national identifier, payment-card, IP-address, and explicit secret patterns in
dynamic prompt material, history, and evidence text. It does not create a
reversible token map or mutate the persisted conversation.

This minimizes data not required for the requested generation; it does not
replace authorization, source ACLs, or a data-processing agreement with the
configured provider.

## Consent transition and audit

`user_privacy_preferences` contains only policy metadata. Every change appends
a non-content row to `privacy_policy_audit_events`. Consent is resolved in the
initialization boundary and propagated to all derived-memory producers, so a
client-provided chat field cannot bypass the policy. The user-facing route uses
only the verified `PrincipalContext`; it accepts no target user identifier.
