"""Fail when production compose services exceed the VPS RAM budget (SRS v2 CON-003, STD-OPS-005)."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

DEFAULT_BUDGET_MB = 6656
UNITS_MB = {"k": 1 / 1024, "m": 1, "g": 1024}


def to_mb(value: str) -> float:
    match = re.fullmatch(r"(\d+(?:\.\d+)?)([kmg])b?", value.strip().lower())
    if not match:
        raise ValueError(f"unsupported memory value: {value!r}")
    return float(match.group(1)) * UNITS_MB[match.group(2)]


def is_one_shot(service: dict) -> bool:
    return "profiles" in service or service.get("restart") in (None, "no")


def check(compose_file: Path, budget_mb: int) -> list[str]:
    services = yaml.safe_load(compose_file.read_text(encoding="utf-8"))["services"]
    errors, total = [], 0.0
    for name, service in services.items():
        if is_one_shot(service):
            continue
        limit = (service.get("deploy") or {}).get("resources", {}).get("limits", {}).get("memory")
        if limit is None:
            errors.append(f"{name}: long-running service has no memory limit")
            continue
        total += to_mb(str(limit))
        print(f"  {name:<16} {limit}")
    print(f"  {'total':<16} {total:.0f}M / budget {budget_mb}M")
    if total > budget_mb:
        errors.append(f"total memory limits {total:.0f}M exceed the {budget_mb}M budget")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--compose", type=Path, default=Path("docker-compose.yml"))
    parser.add_argument("--budget-mb", type=int, default=DEFAULT_BUDGET_MB)
    args = parser.parse_args()
    errors = check(args.compose, args.budget_mb)
    for error in errors:
        print(f"RAM budget: {error}", file=sys.stderr)
    print("RAM budget: " + ("FAIL" if errors else "PASS"))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
