"""
Ingestion Pipeline CLI Entry Point (§10 & §5 of Plan).

Provides command-line commands for running the 5-phase ingestion pipeline:
    1. build-canonical  — Converts raw wiki files into data/canonical/canonical.jsonl
    2. process-chunks   — Reads canonical.jsonl and generates retrieval-ready chunks.jsonl
    3. sync-qdrant      — Generates embeddings and upserts chunks to Qdrant + ingestion.sqlite
    4. cleanup-orphans  — Identifies and purges deleted wiki pages from Qdrant and SQLite
    5. status           — Displays pipeline execution and storage statistics

Usage:
    python -m app.infrastructure.ingestion.cli build-canonical --raw-dir data/raw_wiki
    python -m app.infrastructure.ingestion.cli process-chunks --input data/canonical/canonical.jsonl
    python -m app.infrastructure.ingestion.cli sync-qdrant --input data/chunks/chunks.jsonl
    python -m app.infrastructure.ingestion.cli status
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import List

import click
import structlog

# Force stdout to UTF-8 for Windows console support
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from app.infrastructure.ingestion.canonical import (
    CanonicalWriter,
    build_canonical_page,
    read_canonical_stream,
    write_canonical_stream,
)
from app.infrastructure.ingestion.chunkers import chunk_canonical_page
from app.infrastructure.ingestion.parsers.sanitizer import clean_and_filter_chunk
from app.infrastructure.ingestion.models import CanonicalPage, Chunk, RawPage, RawPageMeta
from app.infrastructure.ingestion.storage import IngestionStateDB, PageStateRecord, QdrantSyncManager

logger = structlog.get_logger(__name__)


# ─────────────────────────────────────────────────────────────
# Click CLI Group
# ─────────────────────────────────────────────────────────────


@click.group(help="Kuchiba Chisa — Ingestion Pipeline CLI v1.1")
def cli() -> None:
    pass


# ─────────────────────────────────────────────────────────────
# Command 1: build-canonical
# ─────────────────────────────────────────────────────────────


@cli.command("build-canonical", help="Build canonical.jsonl from raw wiki files.")
@click.option(
    "--raw-dir",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=Path("data/raw_wiki"),
    help="Directory containing raw wikitext or markdown files.",
)
@click.option(
    "--output",
    type=click.Path(path_type=Path),
    default=Path("data/canonical/canonical.jsonl"),
    help="Output path for canonical.jsonl.",
)
def build_canonical_cmd(raw_dir: Path, output: Path) -> None:
    """Build the Canonical Dataset (data/canonical/canonical.jsonl)."""
    click.echo(f"[+] Building Canonical Dataset from: {raw_dir}")
    click.echo(f"[*] Output target: {output}")

    files = list(raw_dir.rglob("*.wikitext"))
    if not files:
        click.echo(f"[!] No .wikitext input files found under {raw_dir}!", err=True)
        sys.exit(1)

    click.echo(f"[*] Found {len(files)} raw files to process.")

    from app.infrastructure.ingestion.canonical.entity_registry import EntityRegistry
    shared_registry = EntityRegistry()

    canonical_pages: List[CanonicalPage] = []
    page_counter = 1000

    for fpath in files:
        if fpath.name.endswith(".meta.json"):
            continue

        try:
            content = fpath.read_text(encoding="utf-8")
            title = fpath.stem.replace("_", " ").title()

            page_id = page_counter
            categories = []
            revision_id = 1

            # Check for sidecar JSON
            sidecar_name = fpath.name.replace(".wikitext", "").replace(".md", "") + ".meta.json"
            sidecar_path = fpath.parent / sidecar_name
            if sidecar_path.exists():
                try:
                    s_data = json.loads(sidecar_path.read_text(encoding="utf-8"))
                    page_id = s_data.get("page_id", page_id)
                    title = s_data.get("title", title)
                    categories = s_data.get("categories", [])
                    revision_id = s_data.get("revision_id", revision_id)
                except Exception:
                    pass

            meta = RawPageMeta(
                page_id=page_id,
                title=title,
                revision_id=revision_id,
                categories=categories,
                revision_timestamp=datetime.utcnow(),
            )
            raw_page = RawPage(meta=meta, wikitext=content)
            canonical = build_canonical_page(raw_page, registry=shared_registry)
            canonical_pages.append(canonical)
            page_counter += 1
            click.echo(f"  [OK] Parsed: [{canonical.identity.page_type.value}] {title} ({len(canonical.sections)} sections)")
        except Exception as exc:
            click.echo(f"  [FAIL] Failed: {fpath.name} — {exc}", err=True)

    # Pass 2: Post-process metadata synchronization across all canonical pages
    for canonical in canonical_pages:
        c_name = canonical.document_metadata.canonical_name or canonical.identity.title.split("/")[0].strip()
        e_rec = shared_registry.get_entity(c_name)
        if e_rec and e_rec.attributes:
            meta = canonical.document_metadata
            meta.faction = meta.faction or e_rec.attributes.get("faction")
            meta.element = meta.element or e_rec.attributes.get("element")
            meta.rarity = meta.rarity or e_rec.attributes.get("rarity")
            meta.weapon_type = meta.weapon_type or e_rec.attributes.get("weapon")
            meta.region = meta.region or e_rec.attributes.get("region")

    written = write_canonical_stream(canonical_pages, filepath=output, mode="w")
    click.echo(f"[SUCCESS] Successfully wrote {written} CanonicalPage records to {output}")


# ─────────────────────────────────────────────────────────────
# Command 2: process-chunks
# ─────────────────────────────────────────────────────────────


@cli.command("process-chunks", help="Read canonical.jsonl and generate retrieval chunks.")
@click.option(
    "--input",
    "input_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=Path("data/canonical/canonical.jsonl"),
    help="Path to canonical.jsonl input file.",
)
@click.option(
    "--output",
    "output_path",
    type=click.Path(path_type=Path),
    default=Path("data/chunks/chunks.jsonl"),
    help="Output path for chunks.jsonl.",
)
@click.option(
    "--target-size",
    type=int,
    default=256,
    help="Target token size for chunks.",
)
def process_chunks_cmd(input_path: Path, output_path: Path, target_size: int) -> None:
    """Generate structure-aware chunks from canonical.jsonl."""
    click.echo(f"[+] Processing chunks from: {input_path}")
    click.echo(f"[*] Target token size: {target_size}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    pages = list(read_canonical_stream(input_path))

    if not pages:
        click.echo("[!] No CanonicalPage records found in input!", err=True)
        sys.exit(1)

    total_chunks = 0
    kept_chunks = 0
    dropped_chunks = 0

    with open(output_path, "w", encoding="utf-8") as out_f:
        for page in pages:
            chunks = chunk_canonical_page(page, target_token_size=target_size)
            page_kept = 0
            for c in chunks:
                raw_json = c.model_dump_json(by_alias=True)
                clean_json = clean_and_filter_chunk(raw_json)
                if clean_json:
                    out_f.write(clean_json + "\n")
                    kept_chunks += 1
                    page_kept += 1
                else:
                    dropped_chunks += 1
                total_chunks += 1
            click.echo(f"  [OK] Page '{page.identity.title}': {page_kept}/{len(chunks)} valid chunks generated.")

    click.echo(f"[SUCCESS] Total {kept_chunks} valid chunks written to {output_path} ({dropped_chunks} junk chunks dropped by Quality Gate).")


# ─────────────────────────────────────────────────────────────
# Command 3: sync-qdrant
# ─────────────────────────────────────────────────────────────


@cli.command("sync-qdrant", help="Generate embeddings and upsert chunks to Qdrant & SQLite.")
@click.option(
    "--input",
    "input_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=Path("data/chunks/chunks.jsonl"),
    help="Path to chunks.jsonl input file.",
)
@click.option(
    "--db",
    "db_path",
    type=click.Path(path_type=Path),
    default=Path("data/ingestion.sqlite"),
    help="Path to ingestion.sqlite DB.",
)
def sync_qdrant_cmd(input_path: Path, db_path: Path) -> None:
    """Embed chunks and sync vectors to Qdrant & SQLite state DB."""
    click.echo(f"[+] Syncing Qdrant & SQLite from: {input_path}")

    # Read chunks
    chunks: List[Chunk] = []
    with open(input_path, "r", encoding="utf-8") as f:
        for line in f:
            line_str = line.strip()
            if line_str:
                chunks.append(Chunk.model_validate_json(line_str))

    if not chunks:
        click.echo("[!] No chunks found to sync!", err=True)
        sys.exit(1)

    click.echo(f"[*] Found {len(chunks)} chunks to embed and sync.")

    # Instantiate state DB
    state_db = IngestionStateDB(db_path)

    # Initialize FastEmbed embedding adapter
    try:
        from app.infrastructure.embeddings.fastembed_adapter import FastEmbedAdapter

        embedder = FastEmbedAdapter()
        click.echo("  [OK] Initialized FastEmbed model.")
    except Exception as exc:
        click.echo(f"[!] FastEmbed initialization fallback: {exc}")
        embedder = None

    async def _async_sync() -> None:
        sync_manager = QdrantSyncManager()
        chunks_with_vectors = []

        # Generate vectors
        texts_to_embed = [f"{c.context_prefix}\n{c.text_content}" for c in chunks]
        if embedder:
            vectors = await embedder.embed_batch(texts_to_embed, prefix="passage: ")
        else:
            # Synthetic 384-dim dummy vector for testing if FastEmbed model missing
            vectors = [[0.01] * 384 for _ in chunks]

        for chunk, vector in zip(chunks, vectors):
            chunks_with_vectors.append((chunk, vector))

        # Batch upsert to Qdrant
        upserted_count = await sync_manager.upsert_chunk_batch(chunks_with_vectors)

        # Update SQLite State DB
        page_chunks_count: dict[int, int] = {}
        page_samples: dict[int, Chunk] = {}

        for chunk in chunks:
            page_chunks_count[chunk.page_id] = page_chunks_count.get(chunk.page_id, 0) + 1
            page_samples[chunk.page_id] = chunk

        for p_id, count in page_chunks_count.items():
            c_sample = page_samples[p_id]
            rec = PageStateRecord(
                page_id=p_id,
                canonical_slug=c_sample.page_title.lower().replace(" ", "_"),
                title=c_sample.page_title,
                page_type=c_sample.page_type,
                text_hash=c_sample.text_hash,
                chunk_count=count,
                last_updated=datetime.utcnow(),
                status="PROCESSED",
            )
            state_db.upsert_page_state(rec)

        click.echo(f"[SUCCESS] Successfully upserted {upserted_count} points to Qdrant.")
        click.echo(f"[SUCCESS] Updated {len(page_chunks_count)} pages in SQLite state DB ({db_path}).")

    asyncio.run(_async_sync())

    # Explicit memory cleanup & graceful exit
    import gc
    gc.collect()
    sys.exit(0)


# ─────────────────────────────────────────────────────────────
# Command 4: cleanup-orphans
# ─────────────────────────────────────────────────────────────


@cli.command("cleanup-orphans", help="Detect and purge deleted wiki pages from Qdrant & SQLite.")
@click.option(
    "--db",
    "db_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=Path("data/ingestion.sqlite"),
    help="Path to ingestion.sqlite DB.",
)
def cleanup_orphans_cmd(db_path: Path) -> None:
    """Detect deleted pages and purge orphan chunks."""
    click.echo(f"[+] Running Orphan Cleanup on DB: {db_path}")

    state_db = IngestionStateDB(db_path)
    # Check active canonical dataset if present
    canonical_path = Path("data/canonical/canonical.jsonl")
    active_ids = set()

    if canonical_path.exists():
        for p in read_canonical_stream(canonical_path):
            active_ids.add(p.identity.page_id)

    orphans = state_db.detect_orphans(active_ids)
    if not orphans:
        click.echo("[SUCCESS] Zero orphan pages detected. Clean!")
        return

    click.echo(f"[!] Detected {len(orphans)} orphan pages to purge.")

    async def _async_cleanup() -> None:
        sync_manager = QdrantSyncManager()
        orphan_ids = [o.page_id for o in orphans]
        await sync_manager.sync_orphan_deletions(orphan_ids)

        for o in orphans:
            state_db.delete_page_state(o.page_id)
            click.echo(f"  [OK] Purged orphan page_id={o.page_id} ('{o.title}')")

        click.echo(f"[SUCCESS] Orphan cleanup complete. Purged {len(orphans)} pages.")

    asyncio.run(_async_cleanup())


# ─────────────────────────────────────────────────────────────
# Command 5: status
# ─────────────────────────────────────────────────────────────


@cli.command("status", help="Display ingestion pipeline status and storage statistics.")
def status_cmd() -> None:
    """Display overall pipeline status."""
    click.echo("==================================================")
    click.echo("=== Kuchiba Chisa - Ingestion Pipeline Status ===")
    click.echo("==================================================")

    # Check files
    raw_dir = Path("data/raw_wiki")
    canonical_file = Path("data/canonical/canonical.jsonl")
    chunks_file = Path("data/chunks/chunks.jsonl")
    db_file = Path("data/ingestion.sqlite")

    raw_count = len(list(raw_dir.rglob("*.wikitext"))) if raw_dir.exists() else 0
    canonical_size = canonical_file.stat().st_size if canonical_file.exists() else 0
    chunks_size = chunks_file.stat().st_size if chunks_file.exists() else 0

    click.echo(f"[*] Raw Storage ({raw_dir}): {raw_count} wikitext files")
    click.echo(
        f"[*] Canonical Dataset ({canonical_file}): "
        f"{'EXISTS (' + str(round(canonical_size/1024, 1)) + ' KB)' if canonical_file.exists() else 'MISSING'}"
    )
    click.echo(
        f"[*] Chunks Dataset ({chunks_file}): "
        f"{'EXISTS (' + str(round(chunks_size/1024, 1)) + ' KB)' if chunks_file.exists() else 'MISSING'}"
    )

    if db_file.exists():
        state_db = IngestionStateDB(db_file)
        stats = state_db.get_summary_stats()
        click.echo(f"[*] SQLite State DB ({db_file}):")
        click.echo(f"   - Processed Pages: {stats['total_processed_pages']}")
        click.echo(f"   - Total Chunks: {stats['total_chunks_stored']}")
        click.echo(f"   - Quarantined Pages: {stats['quarantined_pages']}")
    else:
        click.echo(f"[*] SQLite State DB ({db_file}): MISSING")

    click.echo("==================================================")


# ─────────────────────────────────────────────────────────────
# Command 6: clear-data
# ─────────────────────────────────────────────────────────────


@cli.command("clear-data", help="Clear raw wiki files, canonical/chunk outputs, and SQLite DB.")
@click.option(
    "--keep-raw",
    is_flag=True,
    help="Keep raw_wiki files, clear only canonical/chunk outputs and SQLite DB.",
)
def clear_data_cmd(keep_raw: bool) -> None:
    """Clear all test/crawled data across pipeline layers."""
    import shutil

    click.echo("==================================================")
    click.echo("=== Kuchiba Chisa - Ingestion Data Cleanup ===")
    click.echo("==================================================")

    raw_dir = Path("data/raw_wiki")
    if raw_dir.exists() and not keep_raw:
        count = 0
        for item in raw_dir.iterdir():
            if item.is_file() and item.name != ".gitkeep":
                item.unlink()
                count += 1
        click.echo(f"  [OK] Cleared {count} raw files from: {raw_dir}")
    elif keep_raw:
        click.echo(f"  [*] Preserved raw files in: {raw_dir}")

    canonical_file = Path("data/canonical/canonical.jsonl")
    if canonical_file.exists():
        canonical_file.unlink()
        click.echo(f"  [OK] Deleted Canonical dataset: {canonical_file}")

    chunks_file = Path("data/chunks/chunks.jsonl")
    if chunks_file.exists():
        chunks_file.unlink()
        click.echo(f"  [OK] Deleted Chunks dataset: {chunks_file}")

    db_file = Path("data/ingestion.sqlite")
    if db_file.exists():
        db_file.unlink()
        click.echo(f"  [OK] Deleted SQLite State DB: {db_file}")

    click.echo("==================================================")
    click.echo("[SUCCESS] Ingestion data cleanup complete!")
    click.echo("==================================================")


# ─────────────────────────────────────────────────────────────
# Command 7: validate-quality
# ─────────────────────────────────────────────────────────────


@cli.command("validate-quality", help="Run 5-Gate Quality Control validation & Quarantine management.")
@click.option(
    "--input",
    "input_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=Path("data/canonical/canonical.jsonl"),
    help="Path to canonical.jsonl input file.",
)
@click.option(
    "--chunks",
    "chunks_path",
    type=click.Path(path_type=Path),
    default=Path("data/chunks/chunks.jsonl"),
    help="Path to chunks.jsonl input file (optional).",
)
@click.option(
    "--quarantine-dir",
    "quarantine_dir",
    type=click.Path(path_type=Path),
    default=Path("data/quarantine"),
    help="Directory to isolate quarantined records.",
)
def validate_quality_cmd(
    input_path: Path,
    chunks_path: Path,
    quarantine_dir: Path,
) -> None:
    """Run 5-Gate Quality Control validation across CanonicalPages and Chunks."""
    from app.infrastructure.ingestion.quality.validator import QualityValidator, QualityStatusEnum

    click.echo(f"[+] Running 5-Gate Quality Control validation on: {input_path}")

    # Read CanonicalPages
    pages: List[CanonicalPage] = []
    with open(input_path, "r", encoding="utf-8") as f:
        for line in f:
            line_str = line.strip()
            if line_str:
                pages.append(CanonicalPage.model_validate_json(line_str))

    # Read Chunks if available
    chunks: List[Chunk] = []
    if chunks_path.exists():
        with open(chunks_path, "r", encoding="utf-8") as f:
            for line in f:
                line_str = line.strip()
                if line_str:
                    chunks.append(Chunk.model_validate_json(line_str))

    validator = QualityValidator(quarantine_dir=quarantine_dir)

    auto_approved = 0
    warnings = 0
    quarantined = 0

    for p in pages:
        report = validator.validate_canonical_page(p)
        if report.status == QualityStatusEnum.AUTO_APPROVED:
            auto_approved += 1
        elif report.status == QualityStatusEnum.APPROVED_WITH_WARNINGS:
            warnings += 1
        else:
            quarantined += 1
            validator.quarantine_page(p, report)

    corpus_report = validator.generate_corpus_report(pages, chunks)

    click.echo("==================================================")
    click.echo("=== 5-Gate Quality Control & Corpus Report ===")
    click.echo("==================================================")
    click.echo(f"  Total Pages Validated:   {len(pages)}")
    click.echo(f"    - AUTO_APPROVED:       {auto_approved}")
    click.echo(f"    - WITH_WARNINGS:       {warnings}")
    click.echo(f"    - QUARANTINED:         {quarantined}")
    click.echo(f"  Total Chunks:            {len(chunks)}")
    click.echo(f"  Avg Chunks per Page:     {corpus_report['avg_chunks_per_page']}")
    click.echo(f"  Avg Tokens per Chunk:    {corpus_report['avg_tokens_per_chunk']}")
    click.echo(f"  Corpus Entity Coverage:  {corpus_report['entity_coverage_pct']}%")
    click.echo(f"  Page Type Distribution:  {corpus_report['page_type_distribution']}")
    click.echo("==================================================")
    click.echo("[SUCCESS] Quality Validation complete!")


@cli.command("enrich-canonical", help="Run offline LLM enrichment on canonical dataset")
@click.option(
    "--input",
    "input_file",
    default="data/canonical/canonical.jsonl",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Path to canonical.jsonl dataset",
)
@click.option(
    "--output",
    "output_file",
    default="data/canonical/canonical.jsonl",
    type=click.Path(dir_okay=False, path_type=Path),
    help="Output path for enriched canonical dataset",
)
def enrich_canonical_command(input_file: Path, output_file: Path) -> None:
    """Enrich Canonical pages using instructor structured LLM extraction."""
    from app.infrastructure.ingestion.enrichment.enricher import enrich_canonical_page
    click.echo(f"[*] Reading canonical stream from {input_file}...")
    pages = read_canonical_stream(input_file)
    enriched_pages = []
    for p in pages:
        enriched = enrich_canonical_page(p)
        enriched_pages.append(enriched)

    write_canonical_stream(enriched_pages, output_file)
    click.echo(f"[SUCCESS] Processed enrichment for {len(enriched_pages)} canonical pages into {output_file}")


# ─────────────────────────────────────────────────────────────
# Command 9: scan-wiki
# ─────────────────────────────────────────────────────────────


@cli.command("scan-wiki", help="Scan MediaWiki categories and generate pre-crawl selection report.")
@click.option(
    "--categories",
    "-c",
    multiple=True,
    help="Specific categories to scan (e.g. -c Resonators -c Factions).",
)
def scan_wiki_cmd(categories: Tuple[str, ...]) -> None:
    """Scan MediaWiki categories and print dry-run selection report."""
    from app.infrastructure.ingestion.crawlers import WikiCrawler

    crawler = WikiCrawler()
    report = asyncio.run(crawler.scan_and_select(categories=list(categories) if categories else None))
    click.echo(report.summary_markdown())


# ─────────────────────────────────────────────────────────────
# Command 10: crawl-wiki
# ─────────────────────────────────────────────────────────────


@cli.command("crawl-wiki", help="Crawl approved lore pages from MediaWiki into raw storage.")
@click.option(
    "--raw-dir",
    type=click.Path(path_type=Path),
    default=Path("data/raw_wiki"),
    help="Target directory for raw wikitext and metadata files.",
)
@click.option(
    "--categories",
    "-c",
    multiple=True,
    help="Specific categories to crawl (e.g. -c Resonators -c Factions).",
)
def crawl_wiki_cmd(raw_dir: Path, categories: Tuple[str, ...]) -> None:
    """Download approved lore pages into data/raw_wiki/."""
    from app.infrastructure.ingestion.crawlers import WikiCrawler

    crawler = WikiCrawler(output_dir=raw_dir)
    report = asyncio.run(crawler.crawl_and_save(categories=list(categories) if categories else None, dry_run=False))
    click.echo(f"[SUCCESS] Downloaded {report.saved_count} clean lore pages into {raw_dir}")


# ─────────────────────────────────────────────────────────────
# Command 11: benchmark
# ─────────────────────────────────────────────────────────────


@cli.command("benchmark", help="Run automated 50-case retrieval accuracy benchmark.")
@click.option(
    "--top-k",
    type=int,
    default=5,
    help="Top K candidates to evaluate (default: 5).",
)
def benchmark_cmd(top_k: int) -> None:
    """Run automated 50-case benchmark on current Vector Store."""
    from app.infrastructure.ingestion.quality.benchmark_runner import BenchmarkRunner

    runner = BenchmarkRunner(top_k=top_k)
    result = asyncio.run(runner.run())
    click.echo(result.generate_report_markdown())


# ─────────────────────────────────────────────────────────────
# Command 12: run-pipeline
# ─────────────────────────────────────────────────────────────


@cli.command("run-pipeline", help="Execute the unified 6-stage master ingestion pipeline.")
@click.option(
    "--mode",
    type=click.Choice(["full", "scan", "crawl", "clean", "reingest", "benchmark"]),
    default="full",
    help="Execution mode (default: full).",
)
@click.option(
    "--raw-dir",
    type=click.Path(path_type=Path),
    default=Path("data/raw_wiki"),
    help="Raw wiki storage directory.",
)
def run_pipeline_cmd(mode: str, raw_dir: Path) -> None:
    """Run master ingestion pipeline end-to-end."""
    from app.infrastructure.ingestion.pipeline import MasterIngestionPipeline

    pipeline = MasterIngestionPipeline(raw_dir=raw_dir)
    summary = asyncio.run(pipeline.run(mode=mode))
    click.echo(summary.to_markdown())


if __name__ == "__main__":
    cli()

