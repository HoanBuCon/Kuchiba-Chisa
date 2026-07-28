"""
Wuthering Waves Wiki Comprehensive Taxonomy & Architecture Audit Scanner.

Performs controlled, rate-limit-safe recursive scanning of MediaWiki Categories:
- Characters by Type (Resonators, NPCs, Deceased Characters, Mentioned Characters)
- Factions
- Lore
- Solaris-3 (World Regions & Locations)
- Quests (Main Quests, Companion Quests, Side Quests)
- Weapons
- Echoes
- Items

Outputs a complete structured JSON report to data/wiki_taxonomy_report.json.
"""

from __future__ import annotations

import json
import time
import urllib.request
import urllib.parse
from pathlib import Path
from typing import Any, Dict, List, Set

FANDOM_API_URL = "https://wutheringwaves.fandom.com/api.php"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)

# Root Categories on Wuthering Waves Wiki
ROOT_TARGET_CATEGORIES = [
    "Characters by Type",
    "Factions",
    "Lore",
    "Solaris-3",
    "Quests",
    "Weapons",
    "Echoes",
    "Items",
    "Locations",
]


def fetch_mediawiki_api(params: Dict[str, str], retries: int = 5) -> Dict[str, Any]:
    """Execute a single throttled MediaWiki API GET request with safe backoff."""
    url_params = urllib.parse.urlencode(params)
    full_url = f"{FANDOM_API_URL}?{url_params}"
    req = urllib.request.Request(full_url, headers={"User-Agent": USER_AGENT})

    for attempt in range(retries):
        try:
            time.sleep(0.5)  # Throttling to protect Fandom API
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = resp.read().decode("utf-8")
                return json.loads(data)
        except Exception as exc:
            if attempt == retries - 1:
                print(f"  [!] Failed fetching {params.get('cmtitle')}: {exc}")
                return {}
            time.sleep((attempt + 1) * 3)
    return {}


def scan_category_deep(category_name: str, max_depth: int = 2, current_depth: int = 1, visited: Set[str] = None) -> Dict[str, Any]:
    """
    Recursively scan a MediaWiki Category for subcategories and direct member pages.
    """
    if visited is None:
        visited = set()

    clean_name = category_name.replace("Category:", "").strip()
    if clean_name.lower() in visited:
        return {"category": clean_name, "pages_count": 0, "subcategories": {}}

    visited.add(clean_name.lower())
    print(f"  {'  ' * (current_depth - 1)}[+] Scanning Category:{clean_name} (depth {current_depth})...")

    cmcontinue = None
    subcategories: List[str] = []
    direct_pages: List[Dict[str, Any]] = []

    while True:
        params = {
            "action": "query",
            "format": "json",
            "list": "categorymembers",
            "cmtitle": f"Category:{clean_name}",
            "cmlimit": "500",
        }
        if cmcontinue:
            params["cmcontinue"] = cmcontinue

        res = fetch_mediawiki_api(params)
        members = res.get("query", {}).get("categorymembers", [])

        for m in members:
            ns = m.get("ns", 0)
            title = m.get("title", "")
            if ns == 14:  # Subcategory
                sub_title = title.replace("Category:", "").strip()
                if sub_title not in subcategories:
                    subcategories.append(sub_title)
            elif ns == 0:  # Page
                direct_pages.append({"pageid": m.get("pageid"), "title": title})

        cmcontinue = res.get("continue", {}).get("cmcontinue")
        if not cmcontinue or not members:
            break

    result: Dict[str, Any] = {
        "category": clean_name,
        "direct_pages_count": len(direct_pages),
        "subcategories_count": len(subcategories),
        "sample_pages": [p["title"] for p in direct_pages[:8]],
        "subcategories": {},
    }

    if current_depth < max_depth and subcategories:
        for sub_cat in subcategories[:15]:  # Top subcategories
            result["subcategories"][sub_cat] = scan_category_deep(
                sub_cat, max_depth=max_depth, current_depth=current_depth + 1, visited=visited
            )

    return result


def main():
    print("==================================================")
    print("=== WUTHERING WAVES WIKI FULL TAXONOMY AUDIT ===")
    print("==================================================")

    visited_cats: Set[str] = set()
    taxonomy_tree: Dict[str, Any] = {}

    for root_cat in ROOT_TARGET_CATEGORIES:
        print(f"\n[+] Auditing Root Domain: Category:{root_cat}")
        root_data = scan_category_deep(root_cat, max_depth=2, current_depth=1, visited=visited_cats)
        taxonomy_tree[root_cat] = root_data

    out_file = Path("data/wiki_taxonomy_report.json")
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(taxonomy_tree, indent=2, ensure_ascii=False), encoding="utf-8")

    print("\n==================================================")
    print(f"[SUCCESS] Deep Audit Completed! Saved to: {out_file}")
    print("==================================================")


if __name__ == "__main__":
    main()
