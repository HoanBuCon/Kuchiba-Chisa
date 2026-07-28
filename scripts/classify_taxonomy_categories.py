"""
Wiki Category Taxonomy Classifier & Whitelist Generator.
Crawls all category tags from raw_wiki metadata, applies RuleEngine filtering,
and generates clean_categories_whitelist.yaml + taxonomy report for LLM review.
"""

from __future__ import annotations
import glob
import json
import os
from pathlib import Path
from typing import Dict, List, Set

from app.infrastructure.ingestion.parsers.sanitizer import get_rule_engine, clean_categories

RAW_WIKI_DIR = Path("data/raw_wiki")
OUTPUT_WHITELIST_PATH = Path("app/infrastructure/ingestion/config/category_whitelist.json")

def harvest_and_classify_categories() -> Dict[str, Any]:
    engine = get_rule_engine()
    meta_files = list(RAW_WIKI_DIR.rglob("*.meta.json"))
    
    all_categories: Set[str] = set()
    category_counts: Dict[str, int] = {}

    for fpath in meta_files:
        try:
            data = json.loads(fpath.read_text(encoding="utf-8"))
            cats = data.get("categories", [])
            for c in cats:
                all_categories.add(c)
                category_counts[c] = category_counts.get(c, 0) + 1
        except Exception:
            pass

    kept_categories: Dict[str, int] = {}
    junk_categories: Dict[str, int] = {}

    for cat in sorted(all_categories):
        if engine.is_junk_category(cat):
            junk_categories[cat] = category_counts[cat]
        else:
            kept_categories[cat] = category_counts[cat]

    print(f"=== WIKI CATEGORY TAXONOMY AUDIT ===")
    print(f"Total Meta Files Examined: {len(meta_files)}")
    print(f"Total Unique Categories Found: {len(all_categories)}")
    print(f"Lore-Relevant Categories (KEPT): {len(kept_categories)}")
    print(f"Junk/Gameplay Categories (DROPPED): {len(junk_categories)}")

    # Save clean whitelist JSON
    OUTPUT_WHITELIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    whitelist_data = {
        "total_categories": len(all_categories),
        "lore_kept_count": len(kept_categories),
        "junk_dropped_count": len(junk_categories),
        "kept_categories": sorted(list(kept_categories.keys())),
        "junk_categories": sorted(list(junk_categories.keys())),
    }
    
    with open(OUTPUT_WHITELIST_PATH, "w", encoding="utf-8") as out_f:
        json.dump(whitelist_data, out_f, indent=2, ensure_ascii=False)

    print(f"[SUCCESS] Exported Category Whitelist to {OUTPUT_WHITELIST_PATH}")
    return whitelist_data


if __name__ == "__main__":
    harvest_and_classify_categories()
