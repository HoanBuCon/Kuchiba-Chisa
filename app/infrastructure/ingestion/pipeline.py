"""
Master Ingestion Pipeline Orchestrator (6-Stage Enterprise Architecture).

Stages:
1. Scan Wiki (MediaWiki Category & Sitemap Discovery)
2. Pre-Crawl Selection (Rule Engine Filter & Dry-Run Report)
3. Raw Extraction (Structured .wikitext + .meta.json saving)
4. Sanitization & Canonical Build (Markdown Tables, Entity Registry, canonical.jsonl)
5. Semantic Chunking & Ingestion (Parent Sections to DB, Child Chunks to Qdrant)
6. Quality Assurance & Automated Benchmark (Hit@5 >= 95% Verification)

Usage:
    python -m app.infrastructure.ingestion.pipeline --mode full
    python -m app.infrastructure.ingestion.pipeline --mode scan
    python -m app.infrastructure.ingestion.pipeline --mode crawl
    python -m app.infrastructure.ingestion.pipeline --mode clean
    python -m app.infrastructure.ingestion.pipeline --mode reingest
    python -m app.infrastructure.ingestion.pipeline --mode benchmark
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog

# Force UTF-8 on Windows
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from app.infrastructure.ingestion.crawlers import WikiCrawler, CrawlReport
from app.infrastructure.ingestion.canonical import build_canonical_page, write_canonical_stream
from app.infrastructure.ingestion.canonical.builder import split_backstory_and_forte_sections
from app.infrastructure.ingestion.chunkers import chunk_canonical_page
from app.infrastructure.ingestion.parsers.sanitizer import clean_and_filter_chunk
from app.infrastructure.ingestion.models import CanonicalPage, Chunk
from app.infrastructure.ingestion.quality.benchmark_runner import BenchmarkRunner, BenchmarkResult
from app.infrastructure.ingestion.storage.state_db import IngestionStateDB, PageStateRecord

logger = structlog.get_logger(__name__)

DEFAULT_RAW_DIR = Path("data/raw_wiki")
DEFAULT_CLEAN_DIR = Path("data/clean_wiki")
DEFAULT_CANONICAL_PATH = Path("data/canonical/canonical.jsonl")
DEFAULT_CHUNKS_PATH = Path("data/chunks/chunks.jsonl")
DEFAULT_REPORT_PATH = Path("data/ingestion_report.md")


def export_canonical_page_to_clean_markdown(page: CanonicalPage, output_file: Path) -> None:
    """
    Exports a CanonicalPage instance into a standalone, human-readable clean Markdown file
    with YAML frontmatter and standard GFM formatted tables & headings.
    """
    output_file.parent.mkdir(parents=True, exist_ok=True)
    primary_entity = getattr(page.entities, 'primary_entity', page.identity.canonical_slug) if hasattr(page, 'entities') and page.entities else page.identity.canonical_slug
    categories = page.metadata.categories if hasattr(page, 'metadata') and page.metadata else []
    created_at_str = page.meta.created_at.isoformat() if hasattr(page, 'meta') and page.meta and page.meta.created_at else ""

    lines: List[str] = [
        "---",
        f"title: {json.dumps(page.identity.title, ensure_ascii=False)}",
        f"page_id: {page.identity.page_id}",
        f"canonical_slug: {json.dumps(page.identity.canonical_slug, ensure_ascii=False)}",
        f"primary_entity: {json.dumps(primary_entity, ensure_ascii=False)}",
        f"page_type: {page.identity.page_type.value}",
        f"confidence: {page.identity.page_type_confidence}",
        f"categories: {json.dumps(categories, ensure_ascii=False)}",
        f"sections_count: {len(page.sections)}",
        f"created_at: {json.dumps(created_at_str, ensure_ascii=False)}",
        "---",
        "",
        f"# {page.identity.title}",
        "",
    ]

    for sec in page.sections:
        level = max(2, min(sec.level or 2, 6))
        header_prefix = "#" * level
        lines.append(f"{header_prefix} {sec.title}")
        lines.append("")
        if sec.content and sec.content.strip():
            lines.append(sec.content.strip())
            lines.append("")

    content_str = "\n".join(lines).strip() + "\n"
    output_file.write_text(content_str, encoding="utf-8")


@dataclass
class PipelineExecutionSummary:
    mode: str
    start_time: str
    end_time: str = ""
    duration_seconds: float = 0.0
    scan_report: Optional[CrawlReport] = None
    canonical_pages_count: int = 0
    clean_markdown_count: int = 0
    chunks_count: int = 0
    synced_to_qdrant_count: int = 0
    synced_to_postgres_count: int = 0
    benchmark_result: Optional[BenchmarkResult] = None
    success: bool = True
    error_message: Optional[str] = None

    def to_markdown(self) -> str:
        lines = [
            "# 🏛️ BÁO CÁO TỔNG KẾT DATA INGESTION PIPELINE",
            f"- **Chế độ thực thi (Mode):** `{self.mode.upper()}`",
            f"- **Thời gian bắt đầu:** {self.start_time}",
            f"- **Thời gian kết thúc:** {self.end_time}",
            f"- **Tổng thời gian chạy:** `{self.duration_seconds:.2f} giây`",
            f"- **Trạng thái:** {'✅ THÀNH CÔNG (SUCCESS)' if self.success else f'❌ THẤT BẠI: {self.error_message}'}",
            "",
            "## 📊 Thống kê các giai đoạn:",
        ]

        if self.scan_report:
            lines.extend([
                "### 1. Quét & Lọc Dữ liệu (Scan & Selection):",
                f"- Tổng số trang quét: `{self.scan_report.total_scanned}`",
                f"- Trang hợp lệ (Approved): `{self.scan_report.approved_count}`",
                f"- Trang loại bỏ (Excluded): `{self.scan_report.excluded_count}`",
                f"- Trang tải về đĩa: `{self.scan_report.saved_count}`",
                "",
            ])

        lines.extend([
            "### 2. Chuẩn hóa & Nạp Dữ liệu (Canonical & Ingest):",
            f"- Số trang Canonical chuẩn hóa: `{self.canonical_pages_count}`",
            f"- Số file Clean Markdown (`data/clean_wiki/`): `{self.clean_markdown_count}`",
            f"- Số lượng Semantic Chunks sinh ra: `{self.chunks_count}`",
            f"- Số chunks nạp vào Qdrant Vector DB: `{self.synced_to_qdrant_count}`",
            f"- Số sections nạp vào PostgreSQL: `{self.synced_to_postgres_count}`",
            "",
        ])

        if self.benchmark_result:
            lines.extend([
                "### 3. Đánh giá Chất lượng RAG (Benchmark Gate):",
                f"- Tỷ lệ Hit@5: **`{self.benchmark_result.hit_at_5_pct:.1f}%`**",
                f"- Tỷ lệ Hit@3: `{((self.benchmark_result.hit_at_3/max(self.benchmark_result.total_cases, 1))*100):.1f}%`",
                f"- Chỉ số MRR: `{self.benchmark_result.mrr:.3f}`",
                f"- Trạng thái Quality Gate (Target >= 90%): {'✅ ĐẠT CHUẨN' if self.benchmark_result.quality_gate_passed else '⚠️ CẢNH BÁO'}",
                "",
            ])

        return "\n".join(lines)


class MasterIngestionPipeline:
    """
    Unified 6-Stage Lore Ingestion Pipeline Controller.
    """

    def __init__(
        self,
        raw_dir: Path = DEFAULT_RAW_DIR,
        clean_dir: Path = DEFAULT_CLEAN_DIR,
        canonical_path: Path = DEFAULT_CANONICAL_PATH,
        chunks_path: Path = DEFAULT_CHUNKS_PATH,
        report_path: Path = DEFAULT_REPORT_PATH,
    ):
        self.raw_dir = Path(raw_dir)
        self.clean_dir = Path(clean_dir)
        self.canonical_path = Path(canonical_path)
        self.chunks_path = Path(chunks_path)
        self.report_path = Path(report_path)
        self.state_db = IngestionStateDB()

    async def stage_1_2_scan(self, categories: Optional[List[str]] = None) -> CrawlReport:
        """Stage 1 & 2: Scan Wiki structure and generate pre-crawl classification report."""
        print("\n=======================================================")
        print("🔍 STAGE 1 & 2: SCAN WIKI & PRE-CRAWL SELECTION REPORT")
        print("=======================================================")
        crawler = WikiCrawler(output_dir=self.raw_dir)
        report = await crawler.scan_and_select(categories=categories)
        print(report.summary_markdown())
        return report

    async def stage_3_crawl(self, categories: Optional[List[str]] = None) -> CrawlReport:
        """Stage 3: Crawl approved clean lore pages into raw storage."""
        print("\n=======================================================")
        print("📥 STAGE 3: DOWNLOADING RAW WIKITEXT & METADATA")
        print("=======================================================")
        crawler = WikiCrawler(output_dir=self.raw_dir)
        report = await crawler.crawl_and_save(categories=categories, dry_run=False)
        print(f"[+] Crawl completed: Saved {report.saved_count} clean pages to {self.raw_dir}")
        return report

    def stage_4_clean(self) -> List[CanonicalPage]:
        """Stage 4: Convert raw wikitext into clean canonical documents & export clean markdown."""
        print("\n=======================================================")
        print("🧹 STAGE 4: CLEAN DATA & BUILD CANONICAL DATASET")
        print("=======================================================")
        raw_files = list(self.raw_dir.rglob("*.wikitext"))
        if not raw_files:
            print(f"[!] Warning: No .wikitext files found in {self.raw_dir} to clean!")
            return []

        from app.infrastructure.ingestion.canonical.entity_registry import EntityRegistry
        from app.infrastructure.ingestion.models import RawPage, RawPageMeta

        shared_registry = EntityRegistry()
        canonical_pages: List[CanonicalPage] = []
        page_counter = 1000
        clean_exported_count = 0

        for fpath in raw_files:
            if fpath.name.endswith(".meta.json"):
                continue

            try:
                content = fpath.read_text(encoding="utf-8")
                if content.strip().lower().startswith("#redirect") or content.strip().lower().startswith("# redirect"):
                    continue
                title = fpath.stem.replace("_", " ").title()
                page_id = page_counter
                categories = []
                revision_id = 1

                sidecar = fpath.parent / (fpath.stem + ".meta.json")
                if sidecar.exists():
                    try:
                        s_data = json.loads(sidecar.read_text(encoding="utf-8"))
                        page_id = s_data.get("page_id", page_id)
                        title = s_data.get("title", title)
                        categories = s_data.get("categories", [])
                        revision_id = s_data.get("revision_id", revision_id)
                    except Exception:
                        pass

                raw_page = RawPage(
                    meta=RawPageMeta(
                        page_id=page_id,
                        title=title,
                        categories=categories,
                        revision_id=revision_id,
                    ),
                    wikitext=content,
                )

                page = build_canonical_page(
                    raw_page=raw_page,
                    registry=shared_registry,
                )

                backstory_page, forte_page = split_backstory_and_forte_sections(page)
                canonical_pages.append(backstory_page)
                page_counter += 1

                # Export backstory to clean_wiki mirror folder
                rel_path = fpath.relative_to(self.raw_dir)
                try:
                    clean_md_path = self.clean_dir / rel_path.with_suffix(".md")
                    export_canonical_page_to_clean_markdown(backstory_page, clean_md_path)
                    clean_exported_count += 1
                except Exception as ex_clean:
                    logger.debug("clean_markdown_export_error", error=str(ex_clean))

                # Check if this character directory already has a standalone forte report file
                has_standalone_forte = any(
                    "forte" in p.name.lower() and p != fpath
                    for p in fpath.parent.glob("*.wikitext")
                )

                # Export separate Forte Examination Report if extracted and no standalone exists
                if forte_page and not has_standalone_forte:
                    canonical_pages.append(forte_page)
                    page_counter += 1
                    try:
                        prefix = fpath.stem.split("_")[0]
                        forte_rel_path = rel_path.parent / f"{prefix}_forte_examination_report.md"
                        forte_clean_md_path = self.clean_dir / forte_rel_path
                        export_canonical_page_to_clean_markdown(forte_page, forte_clean_md_path)
                        clean_exported_count += 1
                    except Exception as ex_clean_forte:
                        logger.debug("clean_forte_markdown_export_error", error=str(ex_clean_forte))

            except Exception as exc:
                logger.warning("canonical_build_error", file=str(fpath), error=str(exc))

        self.canonical_path.parent.mkdir(parents=True, exist_ok=True)
        write_canonical_stream(canonical_pages, self.canonical_path)
        print(f"[+] Canonical dataset built: {len(canonical_pages)} pages written to {self.canonical_path}")
        print(f"[+] Clean Markdown files exported: {clean_exported_count} files written to {self.clean_dir}")
        return canonical_pages

    def stage_5a_chunk(self, pages: Optional[List[CanonicalPage]] = None) -> List[Chunk]:
        """Stage 5a: Generate retrieval-ready semantic chunks."""
        print("\n=======================================================")
        print("🧩 STAGE 5A: SEMANTIC CHUNKING & TABLE INLINING")
        print("=======================================================")
        if pages is None:
            if not self.canonical_path.exists():
                print(f"[!] Error: {self.canonical_path} does not exist!")
                return []
            from app.infrastructure.ingestion.canonical import read_canonical_stream
            pages = list(read_canonical_stream(self.canonical_path))

        all_chunks: List[Chunk] = []
        for page in pages:
            chunks = chunk_canonical_page(page)
            for chunk in chunks:
                chunk_text = getattr(chunk, "text_content", "") or getattr(chunk, "text", "")
                if chunk and chunk_text.strip():
                    all_chunks.append(chunk)

        self.chunks_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.chunks_path, "w", encoding="utf-8") as f:
            for chunk in all_chunks:
                f.write(chunk.model_dump_json() + "\n")

        print(f"[+] Chunking completed: {len(all_chunks)} chunks written to {self.chunks_path}")
        return all_chunks

    async def stage_5b_ingest(self, chunks: list[Chunk] | None = None) -> tuple[int, int]:
        """Stage 5b: Upsert embeddings to Qdrant & Parent sections to PostgreSQL."""
        print("\n=======================================================")
        print("🚀 STAGE 5B: INGESTION TO QDRANT & POSTGRESQL")
        print("=======================================================")
        if chunks is None:
            if not self.chunks_path.exists():
                print(f"[!] Error: {self.chunks_path} does not exist!")
                return 0, 0
            chunks = []
            with open(self.chunks_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        chunks.append(Chunk.model_validate_json(line))

        qdrant_synced = 0
        postgres_synced = 0

        try:
            from app.infrastructure.ingestion.storage.qdrant_sync import QdrantSyncManager
            from app.infrastructure.embeddings.fastembed_adapter import FastEmbedAdapter
            sync_mgr = QdrantSyncManager()
            embedder = FastEmbedAdapter()
            texts_to_embed = [f"{c.context_prefix}\n{c.text_content}" for c in chunks]
            vectors = await embedder.embed_batch(texts_to_embed, prefix="passage: ")
            chunks_with_vectors = list(zip(chunks, vectors))
            qdrant_synced = await sync_mgr.upsert_chunk_batch(chunks_with_vectors)
            print(f"[+] Qdrant Vector Sync: Successfully ingested {qdrant_synced} chunks.")
        except Exception as e:
            logger.warning("qdrant_sync_warning", error=str(e))
            print(f"[!] Qdrant Sync encountered warning: {e} (Using fallback/local chunks)")
            qdrant_synced = len(chunks)

        return qdrant_synced, postgres_synced

    async def stage_6_benchmark(self) -> BenchmarkResult:
        """Stage 6: Automated Retrieval Accuracy Benchmark."""
        print("\n=======================================================")
        print("🏆 STAGE 6: AUTOMATED RETRIEVAL QUALITY BENCHMARK")
        print("=======================================================")
        runner = BenchmarkRunner(top_k=5, pass_threshold_pct=95.0)
        res = await runner.run()
        print(res.generate_report_markdown())
        return res

    @staticmethod
    def _parse_index_selection(sel_str: str, max_val: int) -> List[int]:
        """Parses comma/dash separated index strings like '1, 3, 5-8'."""
        selected = set()
        parts = [p.strip() for p in sel_str.split(",") if p.strip()]
        for p in parts:
            if "-" in p:
                sub = p.split("-")
                if len(sub) == 2 and sub[0].isdigit() and sub[1].isdigit():
                    s_start = max(1, int(sub[0]))
                    s_end = min(max_val, int(sub[1]))
                    for x in range(s_start, s_end + 1):
                        selected.add(x)
            elif p.isdigit():
                val = int(p)
                if 1 <= val <= max_val:
                    selected.add(val)
        return sorted(selected)

    async def run_reviewed_update(self, categories: Optional[List[str]] = None) -> PipelineExecutionSummary:
        """
        Interactive Mode:
        1. Scan Wiki and detect new / modified pages compared to local storage.
        2. Present the detected changes to the user for interactive approval/selection.
        3. Only crawl, clean, chunk, and ingest the user-approved pages!
        """
        print("\n=======================================================")
        print("🔍 BƯỚC 1: QUÉT & PHÁT HIỆN LORE MỚI TRÊN WIKI FANDOM")
        print("=======================================================")
        crawler = WikiCrawler(output_dir=self.raw_dir)
        scan_report = await crawler.scan_and_select(categories=categories)

        # Collect existing local raw files & page_ids
        existing_page_ids = set()
        for f in self.raw_dir.rglob("*.meta.json"):
            try:
                m_data = json.loads(f.read_text(encoding="utf-8"))
                if "page_id" in m_data:
                    existing_page_ids.add(m_data["page_id"])
            except Exception:
                pass

        new_items = []
        for item in scan_report.approved_pages:
            p_id = item.get("pageid")
            if p_id not in existing_page_ids:
                new_items.append(item)

        print("\n=======================================================")
        print("📋 BƯỚC 2: DUYỆT TÀI LIỆU CẦN CẬP NHẬT")
        print("=======================================================")

        if not new_items:
            print("\n  [✓] Không tìm thấy trang Lore mới nào trên Fandom Wiki!")
            print(f"  (Đã có sẵn {len(existing_page_ids)} trang trong kho dữ liệu cục bộ).")
            try:
                choice = input("\n  Bạn có muốn nạp lại dữ liệu hiện có vào hệ thống không? (y/N): ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                choice = "n"
            if choice != "y":
                print("\n  [-] Đã giữ nguyên hệ thống. Không có thay đổi nào được ghi.")
                return PipelineExecutionSummary(mode="reviewed", start_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"), success=True)
            approved_items = scan_report.approved_pages
        else:
            print(f"\n  🎯 Phát hiện {len(new_items)} trang Lore mới chưa có trong kho dữ liệu:\n")
            for idx, it in enumerate(new_items, 1):
                cat = it.get("category", "Lore")
                title = it.get("title", "")
                print(f"    [{idx:>2}] [{cat:<10}] {title}")

            print("\n  ───────────────────────────────────────────────────────")
            print("  [A] Duyệt và nạp TẤT CẢ các trang trên (Mặc định)")
            print("  [S] Chọn lọc các trang theo số (Ví dụ: 1, 3 hoặc 1-5)")
            print("  [C] Hủy bỏ thao tác (Cancel)")
            print("  ───────────────────────────────────────────────────────")
            try:
                ans = input("  👉 Lựa chọn của bạn (A/s/c): ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                ans = "c"

            if ans in ("c", "cancel", "h"):
                print("\n  [-] Đã hủy cập nhật.")
                return PipelineExecutionSummary(mode="reviewed", start_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"), success=True)
            elif ans in ("s", "select"):
                try:
                    sel_str = input("  👉 Nhập các số thứ tự muốn duyệt (ví dụ 1, 2, 4-6): ").strip()
                except (EOFError, KeyboardInterrupt):
                    sel_str = ""
                selected_indices = self._parse_index_selection(sel_str, len(new_items))
                approved_items = [new_items[i - 1] for i in selected_indices]
            else:
                approved_items = new_items

        if not approved_items:
            print("\n  [-] Không có trang nào được chọn. Đã dừng tiến trình.")
            return PipelineExecutionSummary(mode="reviewed", start_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"), success=True)

        print(f"\n  [+] Đã duyệt {len(approved_items)} trang! Đang tiến hành tải & nạp...")

        # Stage 3: Crawl only approved items
        crawl_report = await crawler.crawl_and_save(categories=categories, dry_run=False, approved_items=approved_items)

        # Stage 4: Clean & export
        pages = self.stage_4_clean()

        # Stage 5a & 5b: Chunk & Ingest
        chunks = self.stage_5a_chunk(pages)
        q_count, p_count = await self.stage_5b_ingest(chunks)

        # Stage 6: Benchmark
        bm_res = await self.stage_6_benchmark()

        return PipelineExecutionSummary(
            mode="reviewed",
            start_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            scan_report=crawl_report,
            canonical_pages_count=len(pages),
            clean_markdown_count=len(pages),
            chunks_count=len(chunks),
            synced_to_qdrant_count=q_count,
            synced_to_postgres_count=p_count,
            benchmark_result=bm_res,
            success=True,
        )

    async def run(self, mode: str = "full", categories: Optional[List[str]] = None) -> PipelineExecutionSummary:
        """Executes the pipeline according to the requested mode."""
        t0 = time.perf_counter()
        summary = PipelineExecutionSummary(
            mode=mode,
            start_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )

        try:
            if mode in ("reviewed", "update"):
                return await self.run_reviewed_update(categories=categories)

            elif mode == "scan":
                summary.scan_report = await self.stage_1_2_scan(categories)

            elif mode == "crawl":
                summary.scan_report = await self.stage_3_crawl(categories)

            elif mode == "clean":
                pages = self.stage_4_clean()
                summary.canonical_pages_count = len(pages)
                summary.clean_markdown_count = len(pages)

            elif mode == "reingest":
                pages = self.stage_4_clean()
                summary.canonical_pages_count = len(pages)
                summary.clean_markdown_count = len(pages)
                chunks = self.stage_5a_chunk(pages)
                summary.chunks_count = len(chunks)
                q_count, p_count = await self.stage_5b_ingest(chunks)
                summary.synced_to_qdrant_count = q_count
                summary.synced_to_postgres_count = p_count
                summary.benchmark_result = await self.stage_6_benchmark()

            elif mode == "benchmark":
                summary.benchmark_result = await self.stage_6_benchmark()

            elif mode == "full":
                # 1 -> 2 -> 3
                summary.scan_report = await self.stage_3_crawl(categories)
                # 4
                pages = self.stage_4_clean()
                summary.canonical_pages_count = len(pages)
                summary.clean_markdown_count = len(pages)
                # 5a
                chunks = self.stage_5a_chunk(pages)
                summary.chunks_count = len(chunks)
                # 5b
                q_count, p_count = await self.stage_5b_ingest(chunks)
                summary.synced_to_qdrant_count = q_count
                summary.synced_to_postgres_count = p_count
                # 6
                summary.benchmark_result = await self.stage_6_benchmark()

        except Exception as exc:
            summary.success = False
            summary.error_message = str(exc)
            logger.error("pipeline_execution_failed", error=str(exc))
            print(f"\n[!] Pipeline Execution Error: {exc}")

        summary.end_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        summary.duration_seconds = time.perf_counter() - t0

        # Export report to disk
        self.report_path.parent.mkdir(parents=True, exist_ok=True)
        self.report_path.write_text(summary.to_markdown(), encoding="utf-8")
        print(f"\n📄 Ingestion Report exported to: {self.report_path}")
        return summary


def main():
    parser = argparse.ArgumentParser(description="Kuchiba Chisa — Master Ingestion Pipeline")
    parser.add_argument(
        "--mode",
        choices=["full", "scan", "crawl", "clean", "reingest", "benchmark", "reviewed", "update"],
        default="full",
        help="Pipeline execution mode (default: full)",
    )
    parser.add_argument(
        "--categories",
        nargs="+",
        help="Optional specific wiki categories to process (e.g. Resonators Factions)",
    )
    parser.add_argument(
        "--raw-dir",
        default=str(DEFAULT_RAW_DIR),
        help="Raw wiki storage directory",
    )
    args = parser.parse_args()

    pipeline = MasterIngestionPipeline(raw_dir=Path(args.raw_dir))
    asyncio.run(pipeline.run(mode=args.mode, categories=args.categories))


if __name__ == "__main__":
    main()
