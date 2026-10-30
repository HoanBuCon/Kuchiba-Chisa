# CONTRIBUTING — rules for every contributor (humans and AI agents)

The source of truth is **[SRS v2](SRS_Chisa_v2_Advanced_Agentic_RAG.md)**. Section 14 ("Quy ước hệ thống") is
**mandatory** (STD-GOV-001). When rules conflict: approved SRS > accepted ADR (`docs/adr/`) > section 14 > existing code.

## Before you change anything

- Read the requirement IDs your change touches and cite them in commits/PRs (`Refs: ADV-004, MON-012`).
- Respect the layer rule (SRS §3.5.3): `domain` imports no other layer, `application` imports only `domain`,
  only the composition root imports `infrastructure`. CI enforces it with import-linter.
- **Protected content** (CON-001, STD-AI-003): persona and relationship prompts must stay verbatim
  (`app/domain/services/context_builder.py`, `persona_loader.py`, `data/lore/character_lore/chisa_personality.md`,
  `data/lore/relationship_lore/*.md`). Never edit them without explicit owner approval.
- Never commit secrets, real user data, or prompt/response content in telemetry (STD-SEC-002, MON-013).
- LLM calls go through the LLM gateway only (STD-AI-001). Agent tools are read-only and typed (STD-AI-006).

## Workflow

- Work on a branch off `HBC` (the main working branch; there is no `develop`). `freeze/chisa-v1` is frozen: never commit to it.
- Conventional Commits in English (`type(scope): subject`). Code, comments and logs are English; Chisa's
  user-facing text is Vietnamese and persona-compliant.
- Do not push or merge unless the owner asks.
- **Clean code** (STD-PY-011): one job per function, intention-revealing names, early returns, no dead or
  duplicated code, no unnamed magic numbers, cyclomatic complexity ≤ 10.
- **Clean comments** (STD-PY-012): explain *why*, never restate *what*; keep it to one concise line; no
  commented-out code, banners or emoji; one-sentence docstrings; `TODO` must cite a requirement ID or issue.
- When touching legacy code, clean what you touch (STD-PY-013).
- Every change needs tests. Run the mandatory checks for the change type (SRS §14.10).

## Commands

```bash
./venv/Scripts/python.exe -m pytest -q --ignore=tests/integration   # unit tests (integration needs Docker services)
./venv/Scripts/python.exe -m ruff check <changed files>
./venv/Scripts/python.exe scripts/ruff_debt_ratchet.py               # lint debt must not grow
./venv/Scripts/lint-imports                                          # layer contracts (import-linter)
./chisa dev start | status | stop                                    # local development stack
make test-isolated                                                   # full gates in disposable Docker services
```
