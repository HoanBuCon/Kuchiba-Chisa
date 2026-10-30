"""Fail when a commit in the pull request range is not a Conventional Commit (STD-GIT-002)."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys

TYPES = "feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert"
SUBJECT_RE = re.compile(rf"^({TYPES})(\([a-z0-9._/-]+\))?!?: \S.{{0,99}}$")


def git(*args: str) -> str:
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True).stdout


def resolve_base(explicit: str | None) -> str:
    if explicit:
        return explicit
    target = os.getenv("GITHUB_BASE_REF", "HBC")
    return git("merge-base", "HEAD", f"origin/{target}").strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base")
    base = resolve_base(parser.parse_args().base)
    subjects = git("log", "--no-merges", "--format=%h %s", f"{base}..HEAD").splitlines()
    bad = [line for line in subjects if not SUBJECT_RE.match(line.split(" ", 1)[1])]
    for line in bad:
        print(f"Not a Conventional Commit: {line}", file=sys.stderr)
    print(f"Commit messages: {'FAIL' if bad else 'PASS'} ({len(subjects)} checked)")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
