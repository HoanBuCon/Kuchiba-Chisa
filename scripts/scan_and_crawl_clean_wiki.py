"""
Scan & Clean Crawl Script for Wuthering Waves Wiki.

Scans the Wiki structure, filters out template containers (/Combat), audio dumps (/Voicelines),
skin galleries (/Outfits, /Gallery), and media archives, and crawls ONLY clean lore content:
  - Main Character Pages (e.g. Chixia, Yinlin, Jiyan, Aalto)
  - Backstory Subpages (e.g. Chixia/Backstory)
  - Forte Examination Reports (e.g. Chixia/Forte Examination Report)
  - Lore Subpages (e.g. Chixia/Lore)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

import aiohttp

# Force UTF-8 on Windows console
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

FANDOM_API_URL = "https://wutheringwaves.fandom.com/api.php"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)

# Subpage patterns that are classified as NOISE / TEMPLATES / DUMPS
NOISE_SUBPAGE_PATTERNS: Tuple[str, ...] = (
    "/combat",
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
)

# Subpage patterns that are explicitly APPROVED CLEAN LORE
CLEAN_LORE_SUBPAGE_PATTERNS: Tuple[str, ...] = (
    "/backstory",
    "/forte examination report",
    "/lore",
)


def slugify(text: str) -> str:
    slug = text.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s-]+", "_", slug)
    return slug or "untitled"


def is_clean_lore_page(title: str) -> bool:
    """
    Classify whether a page or subpage is CLEAN LORE or NOISE.

    Rule:
        1. If it's a main page (no '/' in title), it is CLEAN LORE.
        2. If it's a subpage ('/'):
           - Must match CLEAN_LORE_SUBPAGE_PATTERNS (e.g. /Backstory, /Forte Examination Report, /Lore).
           - Must NOT match NOISE_SUBPAGE_PATTERNS (e.g. /Combat, /Outfits, /Voicelines).
    """
    title_lower = title.lower()

    # Main page (e.g. Chixia, Yinlin, Jiyan)
    if "/" not in title:
        return True

    # Check explicitly excluded noise patterns
    for noise in NOISE_SUBPAGE_PATTERNS:
        if noise in title_lower:
            return False

    # Check explicitly allowed lore patterns
    for clean in CLEAN_LORE_SUBPAGE_PATTERNS:
        if clean in title_lower:
            return True

    # Default to False for unknown subpages to keep corpus strictly clean
    return False


async def scan_and_classify_pages(
    session: aiohttp.ClientSession,
    category: str = "Resonators",
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Scan category pages and subpages, returning (clean_lore_pages, excluded_noise_pages)."""
    await asyncio.sleep(2)
    print(f"[+] Scanning Wiki structure for Category: {category}...")

    # Step 1: Fetch primary pages in category with cmcontinue pagination
    primary_pages: List[Dict[str, Any]] = []
    cmcontinue = None

    while True:
        params = {
            "action": "query",
            "format": "json",
            "list": "categorymembers",
            "cmtitle": f"Category:{category}",
            "cmlimit": "500",
        }
        if cmcontinue:
            params["cmcontinue"] = cmcontinue

        fetched_batch = False
        for attempt in range(10):
            try:
                async with session.get(FANDOM_API_URL, params=params) as resp:
                    if resp.status == 429:
                        wait_secs = 5 * (attempt + 1)
                        print(f"  [!] Rate limited (429). Retrying in {wait_secs} seconds...")
                        await asyncio.sleep(wait_secs)
                        continue
                    resp.raise_for_status()
                    data = await resp.json()
                    members = data.get("query", {}).get("categorymembers", [])
                    primary_pages.extend([{"pageid": m["pageid"], "title": m["title"]} for m in members if m.get("ns") == 0])
                    cmcontinue = data.get("continue", {}).get("cmcontinue")
                    fetched_batch = True
                    break
            except Exception as exc:
                if attempt == 9:
                    print(f"  [!] Error fetching category members for {category}: {exc}")
                await asyncio.sleep((attempt + 1) * 3)

        if not fetched_batch or not cmcontinue:
            break

    print(f"  [*] Found {len(primary_pages)} primary pages under Category:{category}.")

    # Step 2: Discover subpages (primarily relevant for Resonators)
    all_pages: List[Dict[str, Any]] = list(primary_pages)
    seen_ids: Set[int] = {p["pageid"] for p in primary_pages}

    if category.lower() in ("resonators", "lore"):
        semaphore = asyncio.Semaphore(2)

        async def _fetch_subpages(title: str) -> List[Dict[str, Any]]:
            async with semaphore:
                await asyncio.sleep(0.3)
                sub_params = {
                    "action": "query",
                    "format": "json",
                    "list": "allpages",
                    "apprefix": f"{title}/",
                    "aplimit": "50",
                    "apfilterredir": "nonredirects",
                }
                for attempt in range(5):
                    try:
                        async with session.get(FANDOM_API_URL, params=sub_params) as sub_resp:
                            if sub_resp.status == 429:
                                await asyncio.sleep((attempt + 1) * 3)
                                continue
                            sub_resp.raise_for_status()
                            sub_data = await sub_resp.json()
                            return sub_data.get("query", {}).get("allpages", [])
                    except Exception:
                        await asyncio.sleep(1)
                return []

        sub_tasks = [_fetch_subpages(p["title"]) for p in primary_pages]
        sub_results = await asyncio.gather(*sub_tasks)

        for sub_list in sub_results:
            for sub in sub_list:
                if sub["pageid"] not in seen_ids:
                    seen_ids.add(sub["pageid"])
                    all_pages.append({"pageid": sub["pageid"], "title": sub["title"]})

    # Step 3: Classify into CLEAN LORE vs EXCLUDED NOISE
    clean_pages: List[Dict[str, Any]] = []
    excluded_pages: List[Dict[str, Any]] = []

    for p in all_pages:
        if is_clean_lore_page(p["title"]):
            clean_pages.append(p)
        else:
            excluded_pages.append(p)

    return clean_pages, excluded_pages


async def fetch_page_details(
    session: aiohttp.ClientSession,
    page_id: int,
    semaphore: asyncio.Semaphore,
) -> tuple[int, str, str, List[str], int, str]:
    """Fetch wikitext content and categories for a single page."""
    async with semaphore:
        await asyncio.sleep(1.0)
        params = {
            "action": "query",
            "format": "json",
            "prop": "revisions|categories",
            "pageids": str(page_id),
            "rvprop": "ids|timestamp|content",
            "rvslots": "main",
            "cllimit": "max",
        }
        for attempt in range(10):
            try:
                async with session.get(FANDOM_API_URL, params=params) as resp:
                    if resp.status == 429:
                        wait_secs = 10 * (attempt + 1)
                        print(f"  [!] Throttled 429 fetching page {page_id}. Waiting {wait_secs}s...")
                        await asyncio.sleep(wait_secs)
                        continue
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
                if attempt == 9:
                    print(f"  [!] Failed to fetch page_id={page_id}: {exc}")
                await asyncio.sleep(5 * (attempt + 1))

        return page_id, "", "", [], 0, ""


async def run_clean_crawl(category: str = "Resonators", output_dir: Path = Path("data/raw_wiki")):
    """Scan structure, report classification, and crawl ONLY clean lore pages."""
    headers = {"User-Agent": USER_AGENT}
    connector = aiohttp.TCPConnector(limit=10)

    async with aiohttp.ClientSession(headers=headers, connector=connector) as session:
        clean_pages, excluded_pages = await scan_and_classify_pages(session, category=category)

        print("==================================================")
        print("=== WUTHERING WAVES WIKI STRUCTURE SCAN REPORT ===")
        print("==================================================")
        print(f"  Total Scanned Pages & Subpages:  {len(clean_pages) + len(excluded_pages)}")
        print(f"  [OK] APPROVED CLEAN LORE PAGES:  {len(clean_pages)}")
        print(f"  [X] EXCLUDED NOISE/TEMPLATE:     {len(excluded_pages)}")
        print("--------------------------------------------------")
        print("  Sample Approved Lore Pages:")
        for p in clean_pages[:10]:
            print(f"    - {p['title']}")
        print("--------------------------------------------------")
        print("  Sample Excluded Noise Pages:")
        for p in excluded_pages[:10]:
            print(f"    - {p['title']}")
        print("==================================================")

        # Clear category-specific subfolder to preserve other category data
        if any("resonator" in c.lower() for c in [category]) or category.lower() == "resonators":
            target_cat_sub = output_dir / "Characters" / "Resonators"
        elif any("npc" in c.lower() for c in [category]) or category.lower() in ("npcs", "npc"):
            target_cat_sub = output_dir / "Characters" / "NPCs"
        elif any("faction" in c.lower() for c in [category]) or category.lower() in ("factions", "faction"):
            target_cat_sub = output_dir / "Factions"
        else:
            target_cat_sub = output_dir / category

        if target_cat_sub.exists():
            import shutil
            shutil.rmtree(target_cat_sub)
            print(f"  [OK] Cleared old category files from: {target_cat_sub}")
        
        target_cat_sub.mkdir(parents=True, exist_ok=True)

        print(f"[+] Crawling ONLY {len(clean_pages)} Clean Lore pages into {output_dir}...")

        semaphore = asyncio.Semaphore(2)
        tasks = [fetch_page_details(session, p["pageid"], semaphore) for p in clean_pages]
        results = await asyncio.gather(*tasks)

        # Import sanitizer to clean raw text right at the crawl phase
        from app.infrastructure.ingestion.parsers.sanitizer import sanitize_wikitext, strip_boilerplate_sections

        known_categories = ["Resonators", "Lore", "Quests", "Locations", "Factions", "Weapons", "Echoes"]

        saved_count = 0
        for page_id, title, content, categories, rev_id, timestamp in results:
            if not content or not title:
                continue

            # Perform raw cleaning to strip templates, html comments, and boilerplate sections
            cleaned_content = sanitize_wikitext(content, page_id=page_id)
            cleaned_content, _ = strip_boilerplate_sections(cleaned_content)

            if not cleaned_content.strip():
                continue

            # 1. Determine Category Directory Path based on crawl category
            cat_lower = category.lower()
            if cat_lower in ("resonators", "resonator"):
                rel_cat_path = Path("Characters") / "Resonators"
                matched_cat = "Resonators"
            elif cat_lower in ("npcs", "npc"):
                rel_cat_path = Path("Characters") / "NPCs"
                matched_cat = "NPCs"
            elif cat_lower in ("factions", "faction"):
                rel_cat_path = Path("Factions")
                matched_cat = "Factions"
            elif cat_lower in ("locations", "solaris-3"):
                rel_cat_path = Path("Locations")
                matched_cat = "Locations"
            elif cat_lower == "lore":
                rel_cat_path = Path("Lore")
                matched_cat = "Lore"
            elif cat_lower == "quests":
                rel_cat_path = Path("Quests")
                matched_cat = "Quests"
            elif cat_lower == "weapons":
                rel_cat_path = Path("Weapons")
                matched_cat = "Weapons"
            elif cat_lower == "echoes":
                rel_cat_path = Path("Echoes")
                matched_cat = "Echoes"
            else:
                rel_cat_path = Path(category)
                matched_cat = category

            # 2. Determine Entity Name and Subpage Stem
            if "/" in title:
                entity_raw, subpage_raw = title.split("/", 1)
                entity_slug = slugify(entity_raw)
                subpage_stem = slugify(subpage_raw)
            else:
                entity_slug = slugify(title)
                subpage_stem = "main"

            # 3. Create Hierarchical Target Directory
            target_dir = output_dir / rel_cat_path / entity_slug
            target_dir.mkdir(parents=True, exist_ok=True)

            wikitext_path = target_dir / f"{page_id}_{subpage_stem}.wikitext"
            wikitext_path.write_text(cleaned_content, encoding="utf-8")

            meta_path = target_dir / f"{page_id}_{subpage_stem}.meta.json"
            meta_data = {
                "page_id": page_id,
                "title": title,
                "slug": f"{entity_slug}_{subpage_stem}",
                "entity": entity_slug,
                "subpage": subpage_stem,
                "category": matched_cat,
                "revision_id": rev_id,
                "timestamp": timestamp,
                "categories": categories,
                "content_length": len(cleaned_content),
            }
            meta_path.write_text(json.dumps(meta_data, indent=2, ensure_ascii=False), encoding="utf-8")
            saved_count += 1

        print("==================================================")
        print(f"[SUCCESS] Saved {saved_count} CLEAN LORE pages to {output_dir}")
        print("==================================================")


async def main():
    parser = argparse.ArgumentParser(description="Scan and crawl clean lore pages from Wuthering Waves Wiki")
    parser.add_argument("--categories", type=str, default="Resonators,Factions", help="Comma-separated Wiki Categories to scan & crawl")
    args = parser.parse_args()

    cat_list = [c.strip() for c in args.categories.split(",") if c.strip()]
    for cat in cat_list:
        print(f"\n🚀 Running Clean Crawl for Category: {cat}")
        await run_clean_crawl(category=cat)
        await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(main())
