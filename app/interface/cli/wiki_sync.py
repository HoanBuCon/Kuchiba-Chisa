"""Operator CLI for the v2 wiki pipeline: `python -m app.interface.cli.wiki_sync <command>`."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import Counter
from collections.abc import Sequence
from contextlib import asynccontextmanager
from dataclasses import asdict, replace
from pathlib import Path

import httpx
from qdrant_client import AsyncQdrantClient

from app.application.ingestion.gold_stage import GoldStage
from app.application.ingestion.image_stage import ImageStage
from app.application.ingestion.report_stage import ReportStage
from app.application.ingestion.silver_stage import SilverStage
from app.application.ingestion.vector_stage import VectorSettings, VectorStage
from app.application.ingestion.wiki_sync import RunStatus, SyncReport, SyncRules, WikiSyncService
from app.config.settings import settings
from app.domain.ingestion.corpus_safety import CorpusSafetyPolicy
from app.domain.ingestion.entity_images import ImageReport
from app.domain.ingestion.page_checks import CheckPolicy
from app.domain.ingestion.release_gates import GateReport, evaluate_data_gate
from app.infrastructure.database.engine import AsyncSessionFactory, engine
from app.infrastructure.database.repositories.knowledge_store import PostgresKnowledgeStore
from app.infrastructure.database.repositories.wiki_inventory import PostgresWikiInventory
from app.infrastructure.database.repositories.wiki_silver import PostgresSilverLedger
from app.infrastructure.embeddings.fastembed_adapter import FastEmbedAdapter
from app.infrastructure.ingestion.bronze_store import FileBronzeStore
from app.infrastructure.ingestion.corpus_explorer import HtmlCorpusExplorer
from app.infrastructure.ingestion.corpus_safety_exceptions import load_page_safety_exceptions
from app.infrastructure.ingestion.entity_image_store import (
    FileImageVault,
    PillowImageInspector,
    load_image_policy,
)
from app.infrastructure.ingestion.gates_config import load_gate_policies
from app.infrastructure.ingestion.gold.config import load_gold_settings
from app.infrastructure.ingestion.gold.gold_store import FileGoldStore
from app.infrastructure.ingestion.gold.passage_embedder import FastEmbedPassageEmbedder
from app.infrastructure.ingestion.gold.staging_index import QdrantStagingIndex
from app.infrastructure.ingestion.gold.token_counter import load_token_counter, tokenizer_sha256
from app.infrastructure.ingestion.gold.vector_cache import FileVectorCache
from app.infrastructure.ingestion.mediawiki_client import MediaWikiClient
from app.infrastructure.ingestion.silver.html_cleaner import HtmlCleaner
from app.infrastructure.ingestion.silver.rules import CONFIG_DIR, load_cleaning_rules
from app.infrastructure.ingestion.silver.silver_store import FileSilverStore
from app.infrastructure.ingestion.wiki_sync_config import WikiSyncConfig, load_wiki_sync_config

SAFETY_EXCEPTIONS = CONFIG_DIR / "safety_exceptions.json"
MAX_REDIRECTS = 3
PREVIEW_DECISIONS = 20
# Offline embedding shares the machine, so it stays on the service's thread budget.
EMBED_THREADS = 2
QDRANT_TIMEOUT_SECONDS = 120


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
    commands.add_parser("assemble", help="build a versioned gold corpus from accepted silver")
    embed = commands.add_parser("embed", help="embed a gold corpus through the vector cache")
    embed.add_argument("--version", help="corpus version; defaults to the newest")
    load = commands.add_parser("load", help="load an embedded corpus into staging collections")
    load.add_argument("--version", help="corpus version; defaults to the newest")
    load.add_argument("--replace", action="store_true", help="recreate existing collections")
    commands.add_parser("images", help="fetch and vet entity images (ING-019)")
    report = commands.add_parser("report", help="render the Corpus Explorer (ING-017)")
    report.add_argument("--version", help="corpus version; defaults to the newest")
    report.add_argument("--previous", help="active corpus version to compare against")
    report.add_argument("--eval", help="retrieval report from evals.retrieval")
    gate = commands.add_parser("gate", help="run the data gate on a corpus version")
    gate.add_argument("--version", help="corpus version; defaults to the newest")
    gate.add_argument("--previous", help="active corpus version to compare against")
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
        safety=CorpusSafetyPolicy(
            exceptions=load_page_safety_exceptions(SAFETY_EXCEPTIONS).exceptions
        ),
    )
    report = await stage.run()
    flagged = [{"title": title, "reasons": list(reasons)} for title, reasons in report.flagged]
    return {"stats": report.stats, "flagged": flagged, "unknown_markup": report.unknown_markup}


async def _assemble() -> dict[str, object]:
    cache_dir = settings.INGESTION_TOKENIZER_CACHE_DIR
    gold_settings = load_gold_settings()
    gold_settings = replace(
        gold_settings,
        tokenizer_sha256=tokenizer_sha256(gold_settings.tokenizer_model, cache_dir),
    )
    root = Path(settings.INGESTION_DATA_DIR)
    stage = GoldStage(
        PostgresWikiInventory(engine, AsyncSessionFactory),
        FileSilverStore(root),
        PostgresSilverLedger(AsyncSessionFactory),
        FileGoldStore(root),
        load_token_counter(gold_settings.tokenizer_model, cache_dir),
        gold_settings,
    )
    report = await stage.run()
    return {"corpus_version": report.corpus_version, "path": report.path, "quality": report.quality}


def _vector_stage() -> tuple[VectorStage, FileGoldStore, AsyncQdrantClient]:
    root = Path(settings.INGESTION_DATA_DIR)
    gold = FileGoldStore(root)
    client = AsyncQdrantClient(
        url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY, timeout=QDRANT_TIMEOUT_SECONDS
    )
    embedder = FastEmbedPassageEmbedder(FastEmbedAdapter(threads=EMBED_THREADS))
    stage = VectorStage(
        gold,
        embedder,
        FileVectorCache(root, embedder.model_id),
        QdrantStagingIndex(client),
        PostgresKnowledgeStore(AsyncSessionFactory),
        VectorSettings(),
    )
    return stage, gold, client


async def _vectors(args: argparse.Namespace) -> dict[str, object]:
    stage, gold, client = _vector_stage()
    version = args.version or gold.latest_version()
    if version is None:
        raise SystemExit("no gold corpus to work on; run assemble first")
    try:
        if args.command == "embed":
            return asdict(await stage.embed(version))
        return asdict(await stage.load(version, replace=args.replace))
    finally:
        await client.close()


async def _images(config: WikiSyncConfig) -> ImageReport:
    root = Path(settings.INGESTION_DATA_DIR)
    source = config.source
    policy = load_image_policy()
    async with httpx.AsyncClient(
        headers={"User-Agent": source.user_agent},
        timeout=source.timeout_seconds,
        follow_redirects=True,
        max_redirects=MAX_REDIRECTS,
    ) as client:
        stage = ImageStage(
            PostgresWikiInventory(engine, AsyncSessionFactory),
            FileBronzeStore(root),
            MediaWikiClient(client, source),
            PillowImageInspector(policy),
            FileImageVault(root),
            policy,
        )
        report = await stage.run()
    _emit({**asdict(report), "passed": report.passed})
    return report


async def _report(args: argparse.Namespace) -> dict[str, object]:
    root = Path(settings.INGESTION_DATA_DIR)
    gold = FileGoldStore(root)
    version = args.version or gold.latest_version()
    if version is None:
        raise SystemExit("no gold corpus to report on; run assemble first")
    evaluation = json.loads(Path(args.eval).read_text(encoding="utf-8")) if args.eval else None
    stage = ReportStage(
        PostgresWikiInventory(engine, AsyncSessionFactory),
        FileBronzeStore(root),
        FileSilverStore(root),
        PostgresSilverLedger(AsyncSessionFactory),
        gold,
        HtmlCorpusExplorer(root),
    )
    return {"report": await stage.run(version, args.previous, evaluation)}


def _data_gate(args: argparse.Namespace) -> GateReport:
    gold = FileGoldStore(Path(settings.INGESTION_DATA_DIR))
    version = args.version or gold.latest_version()
    if version is None:
        raise SystemExit("no gold corpus to gate; run assemble first")
    previous = gold.read_manifest(args.previous) if args.previous else None
    policy, _ = load_gate_policies()
    report = evaluate_data_gate(gold.read_manifest(version), previous, policy)
    _emit(
        {
            "corpus_version": version,
            "passed": report.passed,
            "failures": list(report.failures),
            "checks": {check.name: check.detail for check in report.checks},
        }
    )
    return report


async def _run(args: argparse.Namespace) -> int:
    try:
        if args.command == "status":
            _emit(await _status())
            return 0
        if args.command == "report":
            _emit(await _report(args))
            return 0
        if args.command == "gate":
            return 0 if _data_gate(args).passed else 1
        if args.command in {"embed", "load"}:
            _emit(await _vectors(args))
            return 0
        if args.command == "assemble":
            _emit(await _assemble())
            return 0
        if args.command == "clean":
            _emit(await _clean())
            return 0
        config = load_wiki_sync_config()
        if args.command == "images":
            return 0 if (await _images(config)).passed else 1
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
