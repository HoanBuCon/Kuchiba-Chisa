# TD-036 Ruff Debt Ratchet Verification

Status: **PASS**  
Requirements: `TD-036`, `NFR-OPS-006`, `NFR-OPS-006A`

## Implementation

- Committed baseline: `.ci/ruff_debt_baseline.json`.
- Baseline inventory records total findings and counts by rule, file, and module.
- `scripts/ruff_debt_ratchet.py` fails when full-repository debt exceeds the baseline.
- Semantic/security/correctness rule findings in the explicit blocking set fail regardless of aggregate count.
- CI retains the changed-lines blocking gate and now runs the full debt ratchet as a separate blocking step.
- No legacy Ruff findings were mass-fixed or globally suppressed.

## Evidence

- Historical SRS baseline: 3,861 findings.
- Versioned ratchet baseline: 2,914 findings.
- Blocking semantic findings in baseline: 0.
- Focused ratchet tests: 4 passed.
- Ruff on the new ratchet implementation/tests: passed.

The baseline is not an exemption for new findings. Changed lines remain independently blocking.
