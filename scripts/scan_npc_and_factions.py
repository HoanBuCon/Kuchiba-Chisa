"""Scan Wuthering Waves Wiki API for Category:NPCs and Category:Factions."""

import asyncio
import json
from pathlib import Path
from typing import Dict, List, Set, Any
import aiohttp

FANDOM_API_URL = "https://wutheringwaves.fandom.com/api.php"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) KuchibaChisaBot/1.0"


async def fetch_category_members(
    session: aiohttp.ClientSession, category: str
) -> List[Dict[str, Any]]:
    """Fetch members of a specific MediaWiki category with pagination support."""
    members: List[Dict[str, Any]] = []
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

        for attempt in range(5):
            try:
                async with session.get(FANDOM_API_URL, params=params) as resp:
                    if resp.status == 429:
                        await asyncio.sleep((attempt + 1) * 3)
                        continue
                    resp.raise_for_status()
                    data = await resp.json()
                    query = data.get("query", {})
                    m_list = query.get("categorymembers", [])
                    members.extend(m_list)

                    cmcontinue = data.get("continue", {}).get("cmcontinue")
                    break
            except Exception as exc:
                if attempt == 4:
                    print(f"Error fetching Category:{category}: {exc}")
                await asyncio.sleep(2)

        if not cmcontinue:
            break

    return members


async def fetch_subpages_sample(
    session: aiohttp.ClientSession, prefix: str
) -> List[str]:
    """Fetch subpages starting with prefix/."""
    params = {
        "action": "query",
        "format": "json",
        "list": "allpages",
        "apprefix": f"{prefix}/",
        "aplimit": "50",
        "apfilterredir": "nonredirects",
    }
    try:
        async with session.get(FANDOM_API_URL, params=params) as resp:
            resp.raise_for_status()
            data = await resp.json()
            pages = data.get("query", {}).get("allpages", [])
            return [p["title"] for p in pages]
    except Exception as exc:
        print(f"Error fetching subpages for {prefix}: {exc}")
        return []


async def main():
    headers = {"User-Agent": USER_AGENT}
    connector = aiohttp.TCPConnector(limit=10)

    categories_to_scan = ["NPCs", "Factions"]

    report: Dict[str, Any] = {
        "categories": {},
        "subpage_patterns": {},
        "samples": {},
    }

    async with aiohttp.ClientSession(headers=headers, connector=connector) as session:
        print("[+] Scanning Categories: NPCs and Factions...")

        for cat in categories_to_scan:
            members = await fetch_category_members(session, cat)
            pages = [m["title"] for m in members if m["ns"] == 0]
            subcats = [
                m["title"].replace("Category:", "") for m in members if m["ns"] == 14
            ]

            report["categories"][cat] = {
                "total_members": len(members),
                "total_pages": len(pages),
                "total_subcats": len(subcats),
                "subcategories": subcats,
                "sample_pages": pages[:20],
            }
            print(f"  [+] Category:{cat} -> {len(pages)} pages, {len(subcats)} subcategories.")

        # Check subpages for a sample of NPCs and Factions
        sample_entities = []
        if "NPCs" in report["categories"]:
            sample_entities.extend(report["categories"]["NPCs"]["sample_pages"][:5])
        if "Factions" in report["categories"]:
            sample_entities.extend(report["categories"]["Factions"]["sample_pages"][:5])

        print("\n[+] Checking Subpages for Sample NPCs & Factions...")
        subpage_suffixes: Set[str] = set()

        for ent in sample_entities:
            subpages = await fetch_subpages_sample(session, ent)
            report["samples"][ent] = subpages
            for sp in subpages:
                if "/" in sp:
                    suffix = sp.split("/", 1)[1]
                    subpage_suffixes.add(suffix)

            print(f"  [+] Entity '{ent}' -> {len(subpages)} subpages: {subpages}")

        report["subpage_patterns"] = sorted(list(subpage_suffixes))

    # Save report artifact
    out_file = Path("data/npc_factions_scan_report.json")
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n[SUCCESS] Scan Report saved to: {out_file}")


if __name__ == "__main__":
    asyncio.run(main())
