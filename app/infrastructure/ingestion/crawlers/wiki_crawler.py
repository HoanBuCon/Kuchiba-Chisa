"""
Wiki Crawler & Pre-Crawl Selection Module (Stage 1 & Stage 2 of Ingestion Pipeline).

Features:
1. Discovery: Scans MediaWiki API categories recursively for articles and subpages.
2. Pre-Crawl Selection: Rule Engine filters out noise (/combat, /gallery, /voicelines, etc.)
   and approves high-value lore (/backstory, /forte examination report, /lore, quest chapters).
3. Dry-Run Reporting: Provides a detailed classification breakdown before disk writes.
4. Structured Raw Storage: Saves sanitized .wikitext and .meta.json files into data/raw_wiki/.
5. Rate-Limiting & Concurrency: Uses aiohttp + asyncio.Semaphore to prevent IP blocks.
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import aiohttp
import structlog

logger = structlog.get_logger(__name__)

FANDOM_API_URL = "https://wutheringwaves.fandom.com/api.php"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36 (KuchibaChisaLoreBot/2.0)"
)

# Subpage patterns that are classified as NOISE / GAME MECHANICS / MEDIA DUMPS
NOISE_SUBPAGE_PATTERNS: Tuple[str, ...] = (
    "/combat",
    "/skills",
    "/skill",
    "/attribute",
    "/attributes",
    "/ascension",
    "/outfit",
    "/outfits",
    "/gallery",
    "/voiceline",
    "/voicelines",
    "/audio",
    "/archive",
    "/media",
    "/trophies",
    "/change history",
    "/event stalls",
    "/mini-games",
)

# Subpage patterns that are explicitly APPROVED CLEAN LORE
CLEAN_LORE_SUBPAGE_PATTERNS: Tuple[str, ...] = (
    "/backstory",
    "/forte examination report",
    "/lore",
    "/story",
)

# Target Wiki Category Roots (Focused Pure Lore Dataset)
CORE_CATEGORIES = [
    "Resonators",
    "Factions",
    "Regions",
    "Lore",
]


def slugify(text: str) -> str:
    """Converts a title or subpage to an alphanumeric filesystem slug."""
    slug = text.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "_", slug)
    return slug.strip("_") or "unnamed"


@dataclass
class CrawlReport:
    total_scanned: int = 0
    approved_count: int = 0
    excluded_count: int = 0
    approved_pages: List[Dict[str, Any]] = field(default_factory=list)
    excluded_pages: List[Dict[str, Any]] = field(default_factory=list)
    saved_count: int = 0
    errors: List[str] = field(default_factory=list)
    category_breakdown: Dict[str, Dict[str, int]] = field(default_factory=dict)

    def summary_markdown(self) -> str:
        lines = [
            "# 📊 WIKI SCAN & SELECTION REPORT",
            f"- **Thời gian quét:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"- **Tổng số trang đã quét:** {self.total_scanned}",
            f"- **Số trang HỢP LỆ (Approved Lore):** `{self.approved_count}`",
            f"- **Số trang BỊ LOẠI BỎ (Excluded Noise):** `{self.excluded_count}`",
            f"- **Số trang đã tải về đĩa:** `{self.saved_count}`",
            "",
            "### 📂 Thống kê theo Danh mục:",
        ]
        for cat, stats in self.category_breakdown.items():
            lines.append(f"- **{cat}**: Approved `{stats.get('approved', 0)}` | Excluded `{stats.get('excluded', 0)}`")
        
        if self.errors:
            lines.extend(["", "### ⚠️ Lỗi trong quá trình cào:"])
            for err in self.errors[:10]:
                lines.append(f"- {err}")
        return "\n".join(lines)


class WikiCrawler:
    """
    Asynchronous Fandom MediaWiki Crawler with Pre-Crawl Selection & Sanitization.
    """

    def __init__(
        self,
        output_dir: Path = Path("data/raw_wiki"),
        concurrency: int = 3,
        api_url: str = FANDOM_API_URL,
    ):
        self.output_dir = Path(output_dir)
        self.concurrency = concurrency
        self.api_url = api_url

    async def _fetch_category_members(
        self,
        session: aiohttp.ClientSession,
        category: str,
    ) -> List[Dict[str, Any]]:
        """Fetches all page members for a specific MediaWiki category."""
        members: List[Dict[str, Any]] = []
        cmcontinue = None

        while True:
            params: Dict[str, Any] = {
                "action": "query",
                "list": "categorymembers",
                "cmtitle": f"Category:{category}",
                "cmlimit": "500",
                "format": "json",
            }
            if cmcontinue:
                params["cmcontinue"] = cmcontinue

            try:
                async with session.get(self.api_url, params=params, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                    if resp.status != 200:
                        logger.warning("failed_category_fetch", category=category, status=resp.status)
                        break
                    data = await resp.json()
                    members.extend(data.get("query", {}).get("categorymembers", []))
                    cmcontinue = data.get("continue", {}).get("cmcontinue")
                    if not cmcontinue:
                        break
            except Exception as e:
                logger.error("error_fetching_category", category=category, error=str(e))
                break

        return members

    async def _fetch_subpages_for_page(
        self,
        session: aiohttp.ClientSession,
        title: str,
    ) -> List[Dict[str, Any]]:
        """Discovers subpages for an entity (e.g. Chisa/Backstory)."""
        params = {
            "action": "query",
            "list": "allpages",
            "apprefix": f"{title}/",
            "apfilterredir": "nonredirects",
            "aplimit": "500",
            "format": "json",
        }
        try:
            async with session.get(self.api_url, params=params, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("query", {}).get("allpages", [])
        except Exception:
            pass
        return []

    def classify_page(self, title: str) -> Tuple[bool, str]:
        """
        Rule Engine: Classifies whether a page contains clean canonical lore.
        Returns: (is_approved, reason)
        """
        title_lower = title.lower()

        # Reject common wiki administrative/talk/template namespaces
        if any(ns in title_lower for ns in ("talk:", "template:", "file:", "category:", "module:", "user:")):
            return False, "Administrative or Template Namespace"

        # Check noise subpage blacklist
        for pattern in NOISE_SUBPAGE_PATTERNS:
            if pattern in title_lower:
                return False, f"Noise/Mechanics Pattern: {pattern}"

        # If subpage is explicitly in clean lore list, approve immediately
        for pattern in CLEAN_LORE_SUBPAGE_PATTERNS:
            if pattern in title_lower:
                return True, f"Approved Clean Subpage: {pattern}"

        # If it's a main page without noise suffix, approve
        if "/" not in title:
            return True, "Main Article Page"

        # Secondary subpage not explicitly approved
        return False, "Unapproved Subpage Variant"

    async def scan_and_select(
        self,
        categories: Optional[List[str]] = None,
    ) -> CrawlReport:
        """
        Stage 1 & 2: Scans MediaWiki categories and applies pre-crawl selection rules.
        """
        target_categories = categories or CORE_CATEGORIES
        headers = {"User-Agent": USER_AGENT}
        connector = aiohttp.TCPConnector(limit=self.concurrency)
        report = CrawlReport()
        visited_page_ids: Set[int] = set()

        async with aiohttp.ClientSession(headers=headers, connector=connector) as session:
            for cat in target_categories:
                report.category_breakdown[cat] = {"approved": 0, "excluded": 0}
                print(f"  [*] Đang quét danh mục Fandom: {cat}...", flush=True)
                members = await self._fetch_category_members(session, cat)

                for m in members:
                    page_id = m.get("pageid", 0)
                    if page_id in visited_page_ids:
                        continue
                    visited_page_ids.add(page_id)

                    report.total_scanned += 1
                    title = m.get("title", "")

                    is_app, reason = self.classify_page(title)
                    item = {"pageid": page_id, "title": title, "category": cat, "reason": reason}

                    if is_app:
                        report.approved_count += 1
                        report.approved_pages.append(item)
                        report.category_breakdown[cat]["approved"] += 1
                    else:
                        report.excluded_count += 1
                        report.excluded_pages.append(item)
                        report.category_breakdown[cat]["excluded"] += 1

                # Concurrently discover subpages ONLY for Resonators (e.g. /Backstory, /Forte Examination Report)
                if cat == "Resonators":
                    res_titles = [m.get("title", "") for m in members if "/" not in m.get("title", "") and self.classify_page(m.get("title", ""))[0]]
                    if res_titles:
                        subpage_tasks = [self._fetch_subpages_for_page(session, t) for t in res_titles]
                        subpage_results = await asyncio.gather(*subpage_tasks, return_exceptions=True)
                        for sp_list in subpage_results:
                            if isinstance(sp_list, list):
                                for sp in sp_list:
                                    sp_id = sp.get("pageid", 0)
                                    if sp_id in visited_page_ids:
                                        continue
                                    visited_page_ids.add(sp_id)

                                    report.total_scanned += 1
                                    sp_title = sp.get("title", "")
                                    sp_app, sp_reason = self.classify_page(sp_title)
                                    sp_item = {"pageid": sp_id, "title": sp_title, "category": cat, "reason": sp_reason}

                                    if sp_app:
                                        report.approved_count += 1
                                        report.approved_pages.append(sp_item)
                                        report.category_breakdown[cat]["approved"] += 1
                                    else:
                                        report.excluded_count += 1
                                        report.excluded_pages.append(sp_item)
                                        report.category_breakdown[cat]["excluded"] += 1

        print(f"  [+] Hoàn thành quét {report.total_scanned} trang across {len(target_categories)} danh mục!\n", flush=True)
        return report

    async def _fetch_page_content(
        self,
        session: aiohttp.ClientSession,
        page_id: int,
        semaphore: asyncio.Semaphore,
    ) -> Optional[Dict[str, Any]]:
        """Fetches raw wikitext, categories, revision_id, and last modified timestamp."""
        params = {
            "action": "parse",
            "pageid": str(page_id),
            "prop": "wikitext|categories|revid",
            "format": "json",
        }
        async with semaphore:
            try:
                async with session.get(self.api_url, params=params, timeout=aiohttp.ClientTimeout(total=25)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        parse = data.get("parse", {})
                        title = parse.get("title", "")
                        wikitext = parse.get("wikitext", {}).get("*", "")
                        categories = [c.get("*", "") for c in parse.get("categories", [])]
                        rev_id = parse.get("revid", 1)
                        return {
                            "page_id": page_id,
                            "title": title,
                            "wikitext": wikitext,
                            "categories": categories,
                            "revision_id": rev_id,
                            "timestamp": datetime.utcnow().isoformat(),
                        }
            except Exception as e:
                logger.warning("page_fetch_error", page_id=page_id, error=str(e))
        return None

    async def crawl_and_save(
        self,
        categories: Optional[List[str]] = None,
        dry_run: bool = False,
        approved_items: Optional[List[Dict[str, Any]]] = None,
    ) -> CrawlReport:
        """
        Executes Stage 1 (Scan), Stage 2 (Filter), and Stage 3 (Raw Crawl).
        If dry_run=True, only generates the CrawlReport without writing to disk.
        If approved_items is provided, directly crawls those items.
        """
        if approved_items is not None:
            report = CrawlReport(
                approved_pages=approved_items,
                approved_count=len(approved_items),
                total_scanned=len(approved_items),
            )
        else:
            report = await self.scan_and_select(categories=categories)

        if dry_run:
            return report

        # Import sanitizer for raw cleanup during download
        from app.infrastructure.ingestion.parsers.sanitizer import (
            sanitize_wikitext,
            strip_boilerplate_sections,
        )

        total_pages = len(report.approved_pages)
        print(f"\n  📥 Bắt đầu tải {total_pages} trang Wiki đã chọn lọc về {self.output_dir}...", flush=True)

        headers = {"User-Agent": USER_AGENT}
        connector = aiohttp.TCPConnector(limit=8)
        semaphore = asyncio.Semaphore(8)
        completed_count = 0
        lock = asyncio.Lock()

        async def _download_and_save_worker(session: aiohttp.ClientSession, item: Dict[str, Any]):
            nonlocal completed_count
            page_id = item["pageid"]
            title = item["title"]
            cat = item.get("category", "Lore")

            res = await self._fetch_page_content(session, page_id, semaphore)
            async with lock:
                completed_count += 1
                percent = (completed_count / max(total_pages, 1)) * 100
                print(f"\r  [↓] Đang tải & lưu [{completed_count}/{total_pages}] ({percent:.1f}%): {title[:35]:<35}", end="", flush=True)

            if not res or not res.get("wikitext") or not res.get("title"):
                return

            raw_wikitext = res["wikitext"]
            if raw_wikitext.strip().lower().startswith("#redirect") or raw_wikitext.strip().lower().startswith("# redirect"):
                return

            cleaned = sanitize_wikitext(raw_wikitext, page_id=page_id)
            cleaned, _ = strip_boilerplate_sections(cleaned)

            if not cleaned.strip() or cleaned.strip().lower().startswith("#redirect") or cleaned.strip().lower().startswith("# redirect"):
                return

            matched_cat = cat
            for c in CORE_CATEGORIES:
                if c.lower() in [c_tag.lower() for c_tag in res["categories"]]:
                    matched_cat = c
                    break

            if matched_cat in ("Resonators", "NPCs"):
                rel_cat_path = Path("Characters") / matched_cat
            elif matched_cat == "Regions":
                rel_cat_path = Path("Locations")
            else:
                rel_cat_path = Path(matched_cat)

            if "/" in title:
                entity_raw, subpage_raw = title.split("/", 1)
                entity_slug = slugify(entity_raw)
                subpage_stem = slugify(subpage_raw)
            else:
                entity_slug = slugify(title)
                subpage_stem = "main"

            target_dir = self.output_dir / rel_cat_path / entity_slug
            target_dir.mkdir(parents=True, exist_ok=True)

            wikitext_file = target_dir / f"{page_id}_{subpage_stem}.wikitext"
            wikitext_file.write_text(cleaned, encoding="utf-8")

            meta_file = target_dir / f"{page_id}_{subpage_stem}.meta.json"
            meta_payload = {
                "page_id": page_id,
                "title": title,
                "slug": f"{entity_slug}_{subpage_stem}",
                "entity": entity_slug,
                "subpage": subpage_stem,
                "category": matched_cat,
                "categories": res["categories"],
                "url": f"https://wutheringwaves.fandom.com/wiki/{title.replace(' ', '_')}",
                "revision_id": res["revision_id"],
                "last_modified": res["timestamp"],
            }
            meta_file.write_text(json.dumps(meta_payload, ensure_ascii=False, indent=2), encoding="utf-8")
            async with lock:
                report.saved_count += 1

        async with aiohttp.ClientSession(headers=headers, connector=connector) as session:
            tasks = [_download_and_save_worker(session, p) for p in report.approved_pages]
            await asyncio.gather(*tasks)

        print(f"\n  [✓] Hoàn tất tải & lưu thành công {report.saved_count}/{total_pages} trang Lore sạch!\n", flush=True)

        logger.info(
            "wiki_crawl_completed",
            saved_pages=report.saved_count,
            approved=report.approved_count,
            excluded=report.excluded_count,
        )
        return report


async def run_wiki_crawl(
    output_dir: Path = Path("data/raw_wiki"),
    categories: Optional[List[str]] = None,
    dry_run: bool = False,
) -> CrawlReport:
    """Convenience helper function to run the crawler."""
    crawler = WikiCrawler(output_dir=output_dir)
    return await crawler.crawl_and_save(categories=categories, dry_run=dry_run)
