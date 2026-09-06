"""Audit Ruff legacy debt against a committed, non-increasing baseline."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "ruff-debt-baseline-v1"
DEFAULT_BASELINE = Path(".ci/ruff_debt_baseline.json")
DEFAULT_PATHS = ("app", "tests")

# These findings can change runtime meaning or make code invalid. Legacy style debt
# never exempts them, even when the aggregate count remains below the baseline.
BLOCKING_RULES = frozenset(
    {
        "E902",
        "F601",
        "F602",
        "F621",
        "F622",
        "F631",
        "F632",
        "F633",
        "F634",
        "F701",
        "F702",
        "F704",
        "F706",
        "F707",
        "F811",
        "F821",
        "F822",
        "F823",
        "F831",
        "F901",
    }
)


def _relative_filename(value: str, root: Path) -> str:
    path = Path(value)
    if path.is_absolute():
        try:
            path = path.relative_to(root)
        except ValueError:
            return path.as_posix()
    return path.as_posix()


def _module_for(filename: str) -> str:
    parts = Path(filename).parts
    return "/".join(parts[:2]) if len(parts) >= 2 else filename


def summarize(findings: list[dict[str, Any]], root: Path) -> dict[str, Any]:
    by_rule: Counter[str] = Counter()
    by_file: Counter[str] = Counter()
    by_module: Counter[str] = Counter()
    blocking: Counter[str] = Counter()

    for finding in findings:
        code = str(finding["code"])
        filename = _relative_filename(str(finding["filename"]), root)
        by_rule[code] += 1
        by_file[filename] += 1
        by_module[_module_for(filename)] += 1
        if code in BLOCKING_RULES:
            blocking[code] += 1

    return {
        "total": len(findings),
        "by_rule": dict(sorted(by_rule.items())),
        "by_file": dict(sorted(by_file.items())),
        "by_module": dict(sorted(by_module.items())),
        "blocking_rules": dict(sorted(blocking.items())),
    }


def evaluate(current: dict[str, Any], baseline: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if baseline.get("schema_version") != SCHEMA_VERSION:
        errors.append("unsupported or missing Ruff baseline schema_version")
        return errors

    baseline_audit = baseline.get("audit")
    if not isinstance(baseline_audit, dict) or not isinstance(baseline_audit.get("total"), int):
        errors.append("baseline audit.total must be an integer")
        return errors

    if current["blocking_rules"]:
        errors.append(
            "semantic/security/correctness Ruff findings are blocking: "
            + json.dumps(current["blocking_rules"], sort_keys=True)
        )
    if current["total"] > baseline_audit["total"]:
        errors.append(
            f"Ruff debt increased: current={current['total']} "
            f"baseline={baseline_audit['total']}"
        )
    return errors


def run_ruff(paths: list[str]) -> list[dict[str, Any]]:
    result = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "--output-format=json", *paths],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode not in {0, 1}:
        print(result.stderr, file=sys.stderr)
        raise RuntimeError(f"Ruff audit failed with exit code {result.returncode}")
    value = json.loads(result.stdout or "[]")
    if not isinstance(value, list):
        raise RuntimeError("Ruff JSON output must be a list")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--write-baseline", action="store_true")
    parser.add_argument("paths", nargs="*", default=list(DEFAULT_PATHS))
    args = parser.parse_args()

    root = Path.cwd().resolve()
    audit = summarize(run_ruff(args.paths), root)
    if args.write_baseline:
        if audit["blocking_rules"]:
            print("Refusing to baseline blocking Ruff findings.", file=sys.stderr)
            return 1
        payload = {
            "schema_version": SCHEMA_VERSION,
            "recorded_at": datetime.now(UTC).isoformat(),
            "command": f"python -m ruff check --output-format=json {' '.join(args.paths)}",
            "policy": "NFR-OPS-006A / TD-036",
            "audit": audit,
        }
        args.baseline.parent.mkdir(parents=True, exist_ok=True)
        args.baseline.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote Ruff baseline: {args.baseline} ({audit['total']} findings)")
        return 0

    try:
        baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Unable to load Ruff baseline: {exc}", file=sys.stderr)
        return 2

    errors = evaluate(audit, baseline)
    print(json.dumps(audit, indent=2, sort_keys=True))
    if errors:
        for error in errors:
            print(f"Ruff debt ratchet: FAIL: {error}", file=sys.stderr)
        return 1
    print(
        "Ruff debt ratchet: PASS "
        f"(current={audit['total']}, baseline={baseline['audit']['total']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
