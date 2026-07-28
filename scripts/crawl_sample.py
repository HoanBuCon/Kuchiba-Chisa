"""
Sample MediaWiki Crawler for Wuthering Waves Fandom Wiki.

Crawls real Wiki pages from https://wutheringwaves.fandom.com/api.php,
saves raw wikitext + metadata into data/raw_wiki/, and invokes the ingestion pipeline.

Usage:
    python scripts/crawl_sample.py --limit 500
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any

import aiohttp

# Force UTF-8 on Windows console
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

FANDOM_API_URL = "https://wutheringwaves.fandom.com/api.php"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


def slugify(text: str) -> str:
    slug = text.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s-]+", "_", slug)
    return slug or "untitled"


async def fetch_pages_batch(
    session: aiohttp.ClientSession,
    apcontinue: str = None,
    limit: int = 50,
    category: str = None,
) -> tuple[List[Dict[str, Any]], str]:
    """Fetch a batch of page headers from MediaWiki allpages or categorymembers API."""
    if category:
        params = {
            "action": "query",
            "format": "json",
            "list": "categorymembers",
            "cmtitle": f"Category:{category}",
            "cmlimit": str(limit),
            "cmtype": "page",
        }
        if apcontinue:
            params["cmcontinue"] = apcontinue

        async with session.get(FANDOM_API_URL, params=params) as resp:
            resp.raise_for_status()
            data = await resp.json()
            query = data.get("query", {})
            members = query.get("categorymembers", [])
            # Map cmid/title to pageid/title format
            pages = [{"pageid": m["pageid"], "title": m["title"]} for m in members]
            cont = data.get("continue", {}).get("cmcontinue", "")
            return pages, cont

    params = {
        "action": "query",
        "format": "json",
        "list": "allpages",
        "aplimit": str(limit),
        "apfilterredir": "nonredirects",  # Skip redirects
    }
    if apcontinue:
        params["apcontinue"] = apcontinue

    async with session.get(FANDOM_API_URL, params=params) as resp:
        resp.raise_for_status()
        data = await resp.json()
        query = data.get("query", {})
        pages = query.get("allpages", [])
        cont = data.get("continue", {}).get("apcontinue", "")
        return pages, cont


async def fetch_page_details(
    session: aiohttp.ClientSession,
    page_id: int,
    semaphore: asyncio.Semaphore,
) -> tuple[int, str, str, List[str], int, str]:
    """Fetch wikitext content and categories for a single page."""
    async with semaphore:
        params = {
            "action": "query",
            "format": "json",
            "prop": "revisions|categories",
            "pageids": str(page_id),
            "rvprop": "ids|timestamp|content",
            "rvslots": "main",
            "cllimit": "max",
        }
        try:
            async with session.get(FANDOM_API_URL, params=params) as resp:
                resp.raise_for_status()
                data = await resp.json()
                pages = data.get("query", {}).get("pages", {})
                page_data = pages.get(str(page_id), {})

                title = page_data.get("title", "")
                categories = [
                    c.get("title", "").replace("Category:", "").strip()
                    for c in page_data.get("categories", [])
                ]

                revisions = page_data.get("revisions", [])
                if not revisions:
                    return page_id, title, "", categories, 0, ""

                latest_rev = revisions[0]
                rev_id = latest_rev.get("revid", 0)
                timestamp = latest_rev.get("timestamp", "")
                slots = latest_rev.get("slots", {})
                content = slots.get("main", {}).get("*", "") if "main" in slots else latest_rev.get("*", "")

                return page_id, title, content, categories, rev_id, timestamp
        except Exception as exc:
            print(f"  ❌ Failed to fetch page_id={page_id}: {exc}")
            return page_id, "", "", [], 0, ""


async def fetch_subpage_headers(
    session: aiohttp.ClientSession,
    title: str,
    semaphore: asyncio.Semaphore,
) -> List[Dict[str, Any]]:
    """Fetch text subpages for a parent page (e.g. 'Chixia' -> 'Chixia/Backstory')."""
    async with semaphore:
        params = {
            "action": "query",
            "format": "json",
            "list": "allpages",
            "apprefix": f"{title}/",
            "aplimit": "50",
            "apfilterredir": "nonredirects",
        }
        try:
            async with session.get(FANDOM_API_URL, params=params) as resp:
                resp.raise_for_status()
                data = await resp.json()
                subpages = data.get("query", {}).get("allpages", [])
                # Exclude media/gallery subpages
                return [
                    p for p in subpages
                    if not p["title"].endswith("/Gallery") and not p["title"].endswith("/Audio")
                ]
        except Exception:
            return []


async def crawl_sample_pages(
    target_count: int = 500,
    category: str = None,
    include_subpages: bool = True,
    output_dir: Path = Path("data/raw_wiki"),
):
    """Crawl sample pages and subpages from Wuthering Waves Fandom Wiki."""
    output_dir.mkdir(parents=True, exist_ok=True)
    cat_msg = f" (Category: {category})" if category else ""
    print(f"🚀 Starting crawl of {target_count} pages{cat_msg} from {FANDOM_API_URL}...")
    print(f"📁 Raw output directory: {output_dir.resolve()}")

    headers = {"User-Agent": USER_AGENT}
    connector = aiohttp.TCPConnector(limit=10)

    async with aiohttp.ClientSession(headers=headers, connector=connector) as session:
        page_headers: List[Dict[str, Any]] = []
        apcontinue = None

        print("🔍 Enumerating primary page headers from Wiki API...")
        while len(page_headers) < target_count:
            batch_limit = min(50, target_count - len(page_headers))
            batch, apcontinue = await fetch_pages_batch(
                session,
                apcontinue=apcontinue,
                limit=batch_limit,
                category=category,
            )
            if not batch:
                break
            page_headers.extend(batch)
            print(f"  Fetch header progress: {len(page_headers)}/{target_count} pages...")
            if not apcontinue:
                break

        # Discover subpages for enumerated primary pages if enabled
        if include_subpages:
            print("🔎 Discovering character & lore subpages (e.g. /Backstory, /Combat, /Lore)...")
            sub_sem = asyncio.Semaphore(5)
            sub_tasks = [fetch_subpage_headers(session, p["title"], sub_sem) for p in page_headers]
            sub_results = await asyncio.gather(*sub_tasks)

            seen_ids = {p["pageid"] for p in page_headers}
            subpage_count = 0
            for sub_list in sub_results:
                for sub in sub_list:
                    if sub["pageid"] not in seen_ids:
                        seen_ids.add(sub["pageid"])
                        page_headers.append(sub)
                        subpage_count += 1
            print(f"✨ Discovered {subpage_count} additional subpages (Total pages to crawl: {len(page_headers)})")

        print(f"✅ Enumerated {len(page_headers)} page headers. Fetching wikitext content in parallel...")

        semaphore = asyncio.Semaphore(5)  # 5 concurrent requests (polite rate limit)
        tasks = [
            fetch_page_details(session, p["pageid"], semaphore)
            for p in page_headers[:target_count]
        ]

        results = await asyncio.gather(*tasks)

        saved_count = 0
        for page_id, title, content, categories, rev_id, timestamp in results:
            if not content or not title:
                continue

            slug = slugify(title)
            # Save raw wikitext
            wikitext_path = output_dir / f"{page_id}_{slug}.wikitext"
            wikitext_path.write_text(content, encoding="utf-8")

            # Save metadata sidecar
            meta_path = output_dir / f"{page_id}_{slug}.meta.json"
            meta_data = {
                "page_id": page_id,
                "title": title,
                "slug": slug,
                "revision_id": rev_id,
                "timestamp": timestamp,
                "categories": categories,
                "content_length": len(content),
            }
            meta_path.write_text(json.dumps(meta_data, indent=2, ensure_ascii=False), encoding="utf-8")
            saved_count += 1

        print("=" * 60)
        print(f"✨ Successfully crawled and saved {saved_count} raw pages into {output_dir}")
        print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Crawl Wuthering Waves Wiki pages")
    parser.add_argument("--limit", type=int, default=500, help="Number of pages to crawl (default 500)")
    parser.add_argument("--category", type=str, default=None, help="Specific Wiki Category to crawl (e.g. Resonators)")
    args = parser.parse_args()

    asyncio.run(crawl_sample_pages(target_count=args.limit, category=args.category))
