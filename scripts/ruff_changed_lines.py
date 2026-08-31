"""Fail CI when Ruff reports a finding that intersects changed Python lines."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def resolve_base(explicit_base: str | None) -> str:
    if explicit_base:
        return explicit_base
    github_base = os.getenv("GITHUB_BASE_REF")
    if github_base:
        return run("git", "merge-base", "HEAD", f"origin/{github_base}").stdout.strip()
    return "HEAD"


def changed_lines(base: str) -> dict[Path, set[int]]:
    diff = run("git", "diff", "--no-ext-diff", "--unified=0", base, "--", "*.py").stdout
    lines: dict[Path, set[int]] = defaultdict(set)
    current_path: Path | None = None
    next_line = 0
    for line in diff.splitlines():
        if line.startswith("+++ "):
            value = line[4:]
            current_path = None if value == "/dev/null" else Path(value.removeprefix("b/"))
        elif match := HUNK_RE.match(line):
            next_line = int(match.group(1))
        elif current_path is not None and line and not line.startswith("\\"):
            if line.startswith("+"):
                lines[current_path].add(next_line)
                next_line += 1
            elif not line.startswith("-"):
                next_line += 1
    return lines


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base")
    base = resolve_base(parser.parse_args().base)
    changed = changed_lines(base)
    if not changed:
        print("Ruff changed-lines gate: no changed Python lines.")
        return 0
    result = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "--output-format=json", *map(str, changed)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode not in {0, 1}:
        print(result.stderr, file=sys.stderr)
        return result.returncode
    violations = []
    for finding in json.loads(result.stdout or "[]"):
        path = Path(finding["filename"]).resolve().relative_to(Path.cwd())
        start = finding["location"]["row"]
        end = finding["end_location"]["row"]
        if any(start <= line <= end for line in changed[path]):
            violations.append(finding)
    if not violations:
        print("Ruff changed-lines gate: PASS")
        return 0
    for finding in violations:
        location = finding["location"]
        print(
            f"{finding['filename']}:{location['row']}:{location['column']}: "
            f"{finding['code']} {finding['message']}"
        )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
