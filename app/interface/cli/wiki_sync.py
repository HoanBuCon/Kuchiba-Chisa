"""Operator CLI for the v2 wiki pipeline: `python -m app.interface.cli.wiki_sync <command>`."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import Counter
from collections.abc import Sequence
from contextlib import asynccontextmanager
from pathlib import Path

import httpx

from app.application.ingestion.silver_stage import SilverStage
from app.application.ingestion.wiki_sync import RunStatus, SyncReport, SyncRules, WikiSyncService
from app.config.settings import settings
from app.domain.ingestion.page_checks import CheckPolicy
from app.infrastructure.database.engine import AsyncSessionFactory, engine
from app.infrastructure.database.repositories.wiki_inventory import PostgresWikiInventory
from app.infrastructure.database.repositories.wiki_silver import PostgresSilverLedger
from app.infrastructure.ingestion.bronze_store import FileBronzeStore
from app.infrastructure.ingestion.mediawiki_client import MediaWikiClient
from app.infrastructure.ingestion.silver.html_cleaner import HtmlCleaner
from app.infrastructure.ingestion.silver.rules import load_cleaning_rules
from app.infrastructure.ingestion.silver.silver_store import FileSilverStore
from app.infrastructure.ingestion.wiki_sync_config import WikiSyncConfig, load_wiki_sync_config

MAX_REDIRECTS = 3
PREVIEW_DECISIONS = 20


def _emit(payload: dict[str, object]) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=1) + "\n")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="wiki_sync", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("plan", help="reconcile and list planned fetches without writing")
    sync = commands.add_parser(
        "sync", help="reconcile, persist and fetch changed pages into bronze"
    )
    sync.add_argument(
        "--release-mode", action="store_true", help="use the shorter stabilisation window"
    )
    commands.add_parser("clean", help="clean fetched pages into silver and check them (ING-006)")
    commands.add_parser("status", help="show the last successful run and inventory counts")
    return parser


@asynccontextmanager
async def _service(config: WikiSyncConfig, *, release_mode: bool):
    source = config.source
    async with httpx.AsyncClient(
        headers={"User-Agent": source.user_agent},
        timeout=source.timeout_seconds,
        follow_redirects=True,
        max_redirects=MAX_REDIRECTS,
    ) as client:
        rules = SyncRules(
            catalog=config.catalog,
            classifier=config.classifier,
            policy=config.release_mode_policy if release_mode else config.policy,
        )
        yield WikiSyncService(
            MediaWikiClient(client, source),
            PostgresWikiInventory(engine, AsyncSessionFactory),
            FileBronzeStore(Path(settings.INGESTION_DATA_DIR)),
            rules,
        )


def _summary(report: SyncReport) -> dict[str, object]:
    return {
        "run_id": report.run_id or None,
        "status": report.status,
        "stats": report.stats,
        "planned_by_reason": dict(Counter(d.reason.name for d in report.decisions)),
        "first_planned": [d.title for d in report.decisions[:PREVIEW_DECISIONS]],
        "failures": [{"page_id": pid, "error": error} for pid, error in report.failures],
    }


async def _status() -> dict[str, object]:
    inventory = PostgresWikiInventory(engine, AsyncSessionFactory)
    states = await inventory.load()
    run = await inventory.last_successful_run()
    return {
        "last_successful_run": None
        if run is None
        else {"run_id": run.run_id, "started_at": run.started_at.isoformat(), "stats": run.stats},
        "pages_by_status": dict(Counter(s.status.value for s in states.values())),
        "in_scope_by_family": dict(Counter(s.family for s in states.values() if s.in_text_scope)),
        "never_fetched_in_scope": sum(
            s.in_text_scope and s.fetched_revid is None for s in states.values()
        ),
    }


async def _clean() -> dict[str, object]:
    rules = load_cleaning_rules()
    root = Path(settings.INGESTION_DATA_DIR)
    stage = SilverStage(
        PostgresWikiInventory(engine, AsyncSessionFactory),
        FileBronzeStore(root),
        HtmlCleaner(rules),
        FileSilverStore(root),
        PostgresSilverLedger(AsyncSessionFactory),
        policy=CheckPolicy(residue=rules.residue),
        contracts=rules.contracts,
    )
    report = await stage.run()
    flagged = [{"title": title, "reasons": list(reasons)} for title, reasons in report.flagged]
    return {"stats": report.stats, "flagged": flagged}


async def _run(args: argparse.Namespace) -> int:
    try:
        if args.command == "status":
            _emit(await _status())
            return 0
        if args.command == "clean":
            _emit(await _clean())
            return 0
        config = load_wiki_sync_config()
        async with _service(config, release_mode=getattr(args, "release_mode", False)) as service:
            report = await (service.plan() if args.command == "plan" else service.sync())
        _emit(_summary(report))
        return 0 if report.status in {RunStatus.PLANNED, RunStatus.SUCCEEDED} else 1
    finally:
        await engine.dispose()


def main(argv: Sequence[str] | None = None) -> int:
    return asyncio.run(_run(_parser().parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
