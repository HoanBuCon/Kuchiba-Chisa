# ING-03 Source Governance Verification

Status: **PASS**
Requirements: `FR-ING-001`, `FR-ING-003`, `FR-ING-010`, `ING-03`

## Controls

- Source registry enforces HTTPS URI, owner, license, trust tier, access scope, checksum, crawl schedule, and quarantine by default.
- Curator approval uses verified principal identity and records status/checksum audit transitions.
- Unapproved and cross-owner sources fail closed.
- Corpus prompt-poisoning inspection and immutable curator exceptions remain enforced before staging.
- Canonical `ValidationStage` now detects high-confidence PII/secrets before embedding or storage and records category-only errors without raw sensitive values.
- Existing canonical parser/sanitizer handles Wikitext headings, links, and tables before chunk construction.

## Evidence

- Governance/safety/PII focused suite: 28 passed, 0 failed.
- Parser/sanitizer/chunk-boundary suite: 29 passed, 0 failed.
- Sensitive fixtures: email, API key, and phone were rejected.
- Benign approved lore passed without a sensitive-data false positive.

Previously observed raw-wikitext noise in evaluation data is not hidden or relabelled. It reflects corpus produced outside the fully canonicalized path and remains relevant to `ING-01` parity/retirement; it does not weaken the canonical publish gate added here.
