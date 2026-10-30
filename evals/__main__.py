"""CLI: ``python -m evals validate`` or ``python -m evals run --base-url URL``."""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path

import httpx

from evals.dataset import Category, GoldenSet, load_golden_set
from evals.report import write_report
from evals.runner import run_golden_set
from evals.targets import HttpChatTarget

DEFAULT_DATASET = Path("data/evaluations/golden_v2/golden_v2.yaml")
DEFAULT_OUTPUT = Path("reports/eval")
# Agentic or slow providers can take tens of seconds per turn.
HTTP_TIMEOUT_SECONDS = 120.0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m evals")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("validate", help="validate the golden set and print its composition")
    run = commands.add_parser("run", help="run the golden set against the v1 HTTP API")
    run.add_argument("--base-url", required=True)
    run.add_argument("--category", choices=[category.value for category in Category])
    run.add_argument("--limit", type=int)
    run.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser


def _validate(golden: GoldenSet) -> int:
    for category in Category:
        count = sum(case.category is category for case in golden.cases)
        print(f"{category.value:16} {count}")
    unverified = sum(not case.verified for case in golden.cases)
    print(
        f"Golden set {golden.dataset_version}: {len(golden.cases)} cases, {unverified} unverified"
    )
    return 0


async def _run(golden: GoldenSet, args: argparse.Namespace) -> int:
    cases = [case for case in golden.cases if args.category in (None, case.category.value)]
    cases = cases[: args.limit] if args.limit else cases
    async with httpx.AsyncClient(base_url=args.base_url, timeout=HTTP_TIMEOUT_SECONDS) as client:
        target = HttpChatTarget(client)
        report = await run_golden_set(target, golden, cases)
    stem = f"{golden.dataset_version}-{target.name}-{datetime.now(UTC):%Y%m%dT%H%M%SZ}"
    json_path, markdown_path = write_report(report, args.output, stem)
    print(f"Report: {markdown_path} ({json_path.name})")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    golden = load_golden_set(args.dataset)
    if args.command == "validate":
        return _validate(golden)
    return asyncio.run(_run(golden, args))


if __name__ == "__main__":
    sys.exit(main())
