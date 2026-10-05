# Persona on the grounded lore path — change note (2026-10-05)

## Finding

- The five frozen protected prompt files match their frozen git blobs exactly
  (`reports/TD025_Lore_Answer_Cache_Verification.md`); no prompt was replaced.
- Lore answers lost Chisa's voice on the RAG-06 grounded path
  (`GroundedOutputAssembler`, commit `27cdf12`, 2026-09-06): when a Vietnamese claim
  could not be verified against English evidence, the verbatim English quote was
  delivered on its own (`extractive_quote_fallback`).
- The grounded abstention text (`_GROUNDED_ABSTENTION`, commit `497a808`,
  2026-09-05) used a generic "Mình… Bạn…" voice, contrary to the frozen addressing
  rule (self: "Em", user: "Senpai").
- Visible in development after the 2026-10-05 dev lore ACL backfill made the local
  corpus retrievable; production-equivalent behaviour was unchanged since RAG-06.

## Change (owner-approved options)

1. Verbatim quotes are presented in a fixed persona frame:
   `Em tìm được trong tư liệu gốc nè Senpai: “{quote}”`. Consecutive quotes share one
   frame. The quote text is unaltered.
2. Abstention wording now follows the addressing rule with the same meaning:
   "Em chưa có đủ bằng chứng trong nguồn hiện tại để trả lời chính xác. Senpai có thể
   cho em thêm ngữ cảnh hoặc hỏi theo cách khác không?"

## Grounding is unchanged

`GroundedAnswerEnvelope.answer` (unframed) is still what every check verifies:
prompt-leakage guard, citation guard and claim-evidence guard. The frame is applied
afterwards through `presented_answer`, and it is a server constant, never model
text. Abstention decisions, claim removal and citations are identical.

## Impact on RAG-06 evidence

The RAG-06 review artifacts are not modified. Answer *presentation* now differs from
the reviewed outputs for extractive and abstained cases; claims, citations and
decisions do not. A presentation re-review is recommended before the next formal
evaluation. The lore answer cache grounding version was bumped
(`rag06-grounding-v2` → `v3`) so cached unframed answers are not served.

## Tests

`tests/unit/security/test_persona_contract.py` (frozen blobs, addressing rules, lore,
casual/ambiguous input, abstention, provider-failure fallback, no fallback on
success). Two RAG-06 tests now expect the framed delivery text; their security
assertions are unchanged.
