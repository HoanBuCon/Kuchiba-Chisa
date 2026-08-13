import json
import re
from pathlib import Path
from typing import Dict, Any, Optional
from app.shared.utils.logger import get_logger

log = get_logger(__name__)

def sync_entities_dictionary(
    lore_dir: str = "data/lore",
    chunks_path: str = "data/chunks/chunks.jsonl",
    output_file: str = "data/lore/entities.json"
) -> Dict[str, Any]:
    """
    Scans lore files and chunk metadata to automatically build/update the Entity Knowledge Graph dictionary.
    """
    out_p = Path(output_file)
    out_p.parent.mkdir(parents=True, exist_ok=True)

    # 1. Base Core Character & Lore Entities for Kuchiba Chisa
    entities: Dict[str, Any] = {
        "Kuchiba Chisa": {
            "aliases": ["Chisa", "Kuchiba", "Chía", "Chía Chía", "Bé Chisa", "Chisa Forte", "Mutant Resonator"],
            "type": "CHARACTER",
            "region": "Huanglong",
            "faction": "Startorch Academy",
            "parent": None,
            "related": ["Rover", "Sumika", "Thread Perception", "Honami", "Broadblade"]
        },
        "Rover": {
            "aliases": ["Rover", "Senpai", "Nhà Khai Phá", "Người đồng hành"],
            "type": "CHARACTER",
            "region": "Solaris-3",
            "faction": None,
            "parent": None,
            "related": ["Kuchiba Chisa", "Yangyang", "Chixia", "Baizhi"]
        },
        "Sumika": {
            "aliases": ["Sumika", "Nhật ký Sumika", "Sumika's Diary"],
            "type": "CHARACTER",
            "region": "Huanglong",
            "faction": "Startorch Academy",
            "parent": None,
            "related": ["Kuchiba Chisa", "Honami Loop"]
        },
        "Thread Perception": {
            "aliases": ["Thread Perception", "Sợi Tơ Cấu Trúc", "Sợi Tơ Năng Lượng", "Forte của Chisa", "Năng lực của Chisa"],
            "type": "FORTE",
            "region": None,
            "faction": None,
            "parent": "Kuchiba Chisa",
            "related": ["Kuchiba Chisa", "Broadblade", "Sonoro Sphere"]
        },
        "Broadblade": {
            "aliases": ["Broadblade", "Chiếc kéo khổng lồ", "Kéo khổng lồ", "Vũ khí của Chisa", "Kéo Chisa"],
            "type": "WEAPON",
            "region": None,
            "faction": None,
            "parent": "Kuchiba Chisa",
            "related": ["Kuchiba Chisa", "Thread Perception"]
        },
        "Honami Loop": {
            "aliases": ["Honami", "Vòng lặp Honami", "Vòng lặp", "Breaking the Loop", "Honami Loop"],
            "type": "STORY",
            "region": "Lahai-Roi",
            "faction": None,
            "parent": None,
            "related": ["Kuchiba Chisa", "Sumika", "Sonoro Sphere", "Rover"]
        },
        "Sonoro Sphere": {
            "aliases": ["Sonoro Sphere", "Vùng Sonoro", "Sonoro", "Cầu Tần Số"],
            "type": "WORLD",
            "region": "Solaris-3",
            "faction": None,
            "parent": None,
            "related": ["Tacet Field", "Honami Loop", "Tacet Discord"]
        },
        "Tacet Discord": {
            "aliases": ["Tacet Discord", "Dị Thể Tacet", "TD", "Quái Tacet"],
            "type": "MONSTER",
            "region": "Solaris-3",
            "faction": None,
            "parent": None,
            "related": ["Tacet Field", "Tacet Mark", "Lament", "Sonoro Sphere"]
        },
        "Tacet Field": {
            "aliases": ["Tacet Field", "Vùng Tacet", "Trường Tacet"],
            "type": "WORLD",
            "region": "Solaris-3",
            "faction": None,
            "parent": None,
            "related": ["Tacet Discord", "Waveworn Phenomenon"]
        },
        "Tacet Mark": {
            "aliases": ["Tacet Mark", "Dấu ấn Tacet", "Dấu ấn cộng hưởng"],
            "type": "WORLD",
            "region": "Solaris-3",
            "faction": None,
            "parent": None,
            "related": ["Resonator", "Overclocking"]
        },
        "Resonator": {
            "aliases": ["Resonator", "Người cộng hưởng", "Mutant Resonator"],
            "type": "WORLD",
            "region": "Solaris-3",
            "faction": None,
            "parent": None,
            "related": ["Tacet Mark", "Forte", "Resonance Liberation", "Overclocking"]
        },
        "Solaris-3": {
            "aliases": ["Solaris-3", "Solaris 3", "Hành tinh Solaris-3", "Thế giới Solaris"],
            "type": "WORLD",
            "region": "Solaris-3",
            "faction": None,
            "parent": None,
            "related": ["Huanglong", "Black Shores", "Jinzhou", "Lament"]
        },
        "Huanglong": {
            "aliases": ["Huanglong", "Hoàng Long"],
            "type": "REGION",
            "region": "Huanglong",
            "faction": None,
            "parent": "Solaris-3",
            "related": ["Jinzhou", "Startorch Academy"]
        },
        "Jinzhou": {
            "aliases": ["Jinzhou", "Kim Châu", "Thành phố Jinzhou"],
            "type": "CITY",
            "region": "Huanglong",
            "faction": None,
            "parent": "Huanglong",
            "related": ["Huanglong", "Startorch Academy"]
        },
        "Black Shores": {
            "aliases": ["Black Shores", "Bờ Biển Đen"],
            "type": "FACTION",
            "region": "Solaris-3",
            "faction": "Black Shores",
            "parent": "Solaris-3",
            "related": ["Aalto", "Encore", "Camellya", "Rover"]
        },
        "Startorch Academy": {
            "aliases": ["Startorch Academy", "Học viện Startorch", "Lễ hội Startorch", "Startorch School Festival"],
            "type": "ORGANIZATION",
            "region": "Huanglong",
            "faction": "Startorch Academy",
            "parent": "Huanglong",
            "related": ["Kuchiba Chisa", "Sumika"]
        },
        "Lahai-Roi": {
            "aliases": ["Lahai-Roi", "Lahai Roi", "Lahai"],
            "type": "REGION",
            "region": "Lahai-Roi",
            "faction": None,
            "parent": "Solaris-3",
            "related": ["Honami Loop", "Sonoro Sphere"]
        },
        "Lament": {
            "aliases": ["Lament", "Thảm họa Lament", "The Lament"],
            "type": "EVENT",
            "region": "Solaris-3",
            "faction": None,
            "parent": None,
            "related": ["Waveworn Phenomenon", "Tacet Discord", "Solaris-3"]
        },
        "Overclocking": {
            "aliases": ["Overclocking", "Bộc phát tần số", "Quá tải tần số", "Overclock"],
            "type": "PHENOMENON",
            "region": None,
            "faction": None,
            "parent": None,
            "related": ["Resonator", "Tacet Mark"]
        }
    }

    # 2. Extract from chunks.jsonl if present
    c_path = Path(chunks_path)
    if c_path.exists():
        try:
            with open(c_path, "r", encoding="utf-8") as f:
                for line in f:
                    c = json.loads(line)
                    canon = c.get("canonical_name") or c.get("page_title")
                    if not canon:
                        continue
                    
                    if len(canon) < 3 or canon in ["She", "He", "They", "It", "You", "The", "And", "But", "For"]:
                        continue

                    etype = c.get("entity_type") or c.get("page_type") or "GENERIC"
                    region = c.get("region")
                    faction = c.get("faction")
                    chunk_ents = [e for e in (c.get("entities") or []) if e != canon and len(e) > 2]

                    if canon not in entities:
                        entities[canon] = {
                            "aliases": [canon],
                            "type": etype,
                            "region": region,
                            "faction": faction,
                            "parent": None,
                            "related": chunk_ents[:10]
                        }
                    else:
                        # Append any new related entities
                        existing_related = set(entities[canon].get("related", []))
                        for e in chunk_ents:
                            if e not in existing_related:
                                entities[canon]["related"].append(e)
                                existing_related.add(e)
        except Exception as e:
            log.warning("Failed to parse chunks.jsonl for entity sync", error=str(e))

    with open(out_p, "w", encoding="utf-8") as f:
        json.dump(entities, f, ensure_ascii=False, indent=2)

    log.info("Entity dictionary synchronized successfully", total_entities=len(entities), path=str(out_p))
    return entities
