# Evaluation harness and golden v2 (SRS v2 §6.5, §9, R0.4)

`evals/` is an offline harness: it runs a golden set against a target system and writes a versioned report
(evaluator version, sample size, 95% Wilson intervals, a fixed manual-review sample). The app never imports it
(import-linter contract).

## Golden v2

`data/evaluations/golden_v2/golden_v2.yaml`, ground truth from the wiki snapshot `wuwa-wiki-20261030`.

| Category | Cases | Gates |
| --- | --- | --- |
| lore_single_hop | 12 | QUAL-001, QUAL-003 |
| enumeration | 6 | QUAL-007 (quest lists, "Honami" style) |
| multi_hop | 6 | QUAL-007, QUAL-009 |
| dialogue_detail | 6 | QUAL-007 |
| out_of_scope | 6 | QUAL-004 |
| memory | 4 | QUAL-008 (2 need multiple sessions) |
| persona | 4 | QUAL-005, PER-003 |

Languages: Vietnamese, English, Vietnamese without diacritics, teencode. Cases cite wiki **page ids**, so they
survive corpus rebuilds; every `verified: true` answer fact was checked to appear in the cited pages.

### Owner review before approval

The set is `approval.status: draft` and must not gate a release until the owner:

1. Confirms the three `verified: false` cases: `enum-002` (Honami quest list completeness), `oos-006`
   (no canon founding date for Startorch), `persona-002` (whether a user may change how Chisa addresses them).
2. Checks Vietnamese surface forms in `expected_facts` (for example in-game Vietnamese names of attributes).
3. Adds or removes cases, then sets `approval` to `approved` with name and date.

## Scoring

- **Facts**: each fact matches if any surface form appears in the answer, ignoring case and diacritics.
  A case is correct when fact recall reaches `min_fact_recall` and the target did not abstain.
- **Abstain**: the target's own signal, else the dataset `abstain_markers`. This is a heuristic, so the
  manual-review sample must be read on every baseline run.
- **Retrieval**: Hit@5 / MRR@10 over evidence page ids. The v1 API exposes only cited evidence, so for v1
  this is a *citation* hit rate, not true retrieval recall; R1 adds a retrieval-level target.
- **Persona**: requires "Senpai" and none of the case's forbidden patterns.

No LLM judge is used yet; groundedness and citation precision (QUAL-001/002) arrive with the evidence ledger.

## Running

```bash
./venv/Scripts/python.exe -m evals validate
./venv/Scripts/python.exe -m evals run --base-url http://localhost:8000 --category lore_single_hop
```

Reports go to `reports/eval/` (gitignored). Runs call the real LLM through the target, so they cost money and
run sequentially.
