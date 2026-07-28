"""
Dynamic Wuthering Waves Wiki Structure Scanner & Diagram Generator.

Scans raw wiki files (data/lore, data/raw_wiki) or canonical data (data/canonical/canonical.jsonl),
extracts actual page types, infobox schemas, heading hierarchies, table structures, and entity relationships,
and auto-generates a Markdown document with Mermaid diagrams detailing the exact Wiki structure.
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

# Force stdout to UTF-8
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app.infrastructure.ingestion.canonical.builder import build_canonical_page
from app.infrastructure.ingestion.models.canonical_page import CanonicalPage, ContentTypeEnum, PageTypeEnum
from app.infrastructure.ingestion.models.raw_page import RawPage, RawPageMeta
from app.infrastructure.ingestion.parsers.classifier import classify_page_type
from app.infrastructure.ingestion.parsers.sanitizer import sanitize_wikitext


from datetime import datetime

def scan_lore_directory(data_dir: Path) -> List[CanonicalPage]:
    """Scan all markdown and json files in data_dir and parse them into CanonicalPages."""
    pages: List[CanonicalPage] = []
    if not data_dir.exists():
        return pages

    md_files = list(data_dir.rglob("*.md")) + list(data_dir.rglob("*.wikitext"))
    for idx, fpath in enumerate(md_files, start=1000):
        try:
            content = fpath.read_text(encoding="utf-8")
            meta_path = fpath.with_suffix(".meta.json")
            categories = []
            if meta_path.exists():
                meta_json = json.loads(meta_path.read_text(encoding="utf-8"))
                categories = meta_json.get("categories", [])

            title = fpath.stem.replace("_", " ").title()
            raw_page = RawPage(
                meta=RawPageMeta(
                    page_id=idx,
                    title=title,
                    revision_id=100000 + idx,
                    revision_timestamp=datetime.utcnow(),
                    categories=categories,
                ),
                wikitext=content,
            )
            canonical = build_canonical_page(raw_page)
            pages.append(canonical)
        except Exception as exc:
            print(f"[!] Error parsing {fpath.name}: {exc}")

    return pages


def scan_canonical_jsonl(jsonl_path: Path) -> List[CanonicalPage]:
    """Read existing canonical pages from canonical.jsonl if available."""
    pages: List[CanonicalPage] = []
    if not jsonl_path.exists():
        return pages

    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            line_str = line.strip()
            if line_str:
                pages.append(CanonicalPage.model_validate_json(line_str))

    return pages


def analyze_wiki_structure(pages: List[CanonicalPage]) -> str:
    """Analyze CanonicalPages and build dynamic Mermaid/Markdown structure report."""
    page_type_counts: Counter[str] = Counter()
    content_type_counts: Counter[str] = Counter()
    category_counts: Counter[str] = Counter()
    infobox_keys: Dict[str, Set[str]] = defaultdict(set)
    heading_hierarchy: Dict[str, List[str]] = defaultdict(list)
    relationships_found: Set[Tuple[str, str, str]] = set()

    for p in pages:
        pt = p.identity.page_type.value
        page_type_counts[pt] += 1

        for cat in p.document_metadata.categories:
            category_counts[cat] += 1

        if p.infobox:
            for k in p.infobox.keys():
                infobox_keys[pt].add(k)

        for sec in p.sections:
            content_type_counts[sec.content_type.value] += 1
            heading_hierarchy[pt].append(sec.title)

        for rel in p.relationships:
            relationships_found.add((rel.source, rel.relation, rel.target))

    # Construct Mermaid Mindmap
    mindmap_lines = ["mindmap", "  root((Wuthering Waves Wiki Structure))"]
    for pt, count in page_type_counts.most_common():
        mindmap_lines.append(f"    {pt}[Page Type: {pt} ({count} pages)]")
        keys = list(infobox_keys.get(pt, []))[:5]
        if keys:
            mindmap_lines.append(f"      Infobox Keys: {', '.join(keys)}")
        headings = list(set(heading_hierarchy.get(pt, [])))[:4]
        if headings:
            mindmap_lines.append(f"      Common Headings: {', '.join(headings)}")

    mindmap_str = "\n".join(mindmap_lines)

    # Construct Mermaid Flowchart for Ingestion Routing
    flowchart_str = """flowchart TD
    subgraph RawData ["Wuthering Waves Raw Data Layer"]
        WikiPages["Wiki Pages / Wikitext"] --> Sanitizer["Sanitizer & Stripper"]
        Sanitizer --> SectionExtractor["Section & Table Parser"]
    end

    subgraph CanonicalLayer ["Canonicalization Layer (canonical.jsonl)"]
        SectionExtractor --> Classifier["PageType Classifier"]
        Classifier --> EntityRes["Entity & Alias Registry"]
        EntityRes --> GoldenCanonical[("Canonical Dataset\ndata/canonical/canonical.jsonl")]
    end

    subgraph Downstream ["Structure-Aware Chunking & Storage"]
        GoldenCanonical --> Router{"Content-Type Router"}
        Router -- "TABLE" --> TableInliner["TableInlinerChunker"]
        Router -- "DIALOGUE" --> DialogueChunker["DialogueChunker"]
        Router -- "PROSE / LIST" --> GenericChunker["GenericChunker"]
        Router -- "ATOMIC" --> AtomicChunker["AtomicChunker (Unsplit)"]

        TableInliner --> ContextPrefix["Context Prefix Injection"]
        DialogueChunker --> ContextPrefix
        GenericChunker --> ContextPrefix
        AtomicChunker --> ContextPrefix

        ContextPrefix --> Qdrant[("Qdrant Vector Storage\nchisa_characters | chisa_lore | chisa_gameplay")]
    end"""

    # Construct Entity ER Diagram
    er_lines = ["erDiagram"]
    if relationships_found:
        for src, rel, tgt in list(relationships_found)[:10]:
            clean_src = re.sub(r"[^\w]", "_", src)
            clean_tgt = re.sub(r"[^\w]", "_", tgt)
            er_lines.append(f"    {clean_src} ||--o{{ {clean_tgt} : {rel.lower()}")
    else:
        er_lines.extend([
            "    RESONATOR ||--o{ WEAPON : equips",
            "    RESONATOR ||--o{ ECHO : equips",
            "    RESONATOR }|--|| FACTION : member_of",
            "    RESONATOR }|--|| REGION : originates_from",
            "    FACTION }|--|| REGION : located_in",
            "    QUEST }|--|| REGION : takes_place_in",
        ])
    er_str = "\n".join(er_lines)

    # Table breakdown
    table_rows = []
    for pt, count in page_type_counts.most_common():
        sample_headings = ", ".join(list(set(heading_hierarchy.get(pt, [])))[:3])
        sample_info = ", ".join(list(infobox_keys.get(pt, []))[:3]) or "None"
        table_rows.append(f"| `{pt}` | {count} | `{sample_info}` | `{sample_headings}` |")

    table_str = "\n".join(table_rows)

    doc_content = f"""# STRUCTURAL DIAGRAM & TAXONOMY: WUTHERING WAVES WIKI

> **Tự động trích xuất từ dữ liệu Wiki**: {len(pages)} trang đã được phân tích.  
> **Thời gian tạo**: 2026-07-26  

---

## 1. PHÂN LOẠI CẤU TRÚC WIKI (DYNAMIC WIKI TAXONOMY MINDMAP)

```mermaid
{mindmap_str}
```

---

## 2. LUỒNG XỬ LÝ DỮ LIỆU WIKI (INGESTION PIPELINE FLOWCHART)

```mermaid
{flowchart_str}
```

---

## 3. THỐNG KÊ CHI TIẾT CÁC PHÂN LOẠI TRANG (PAGE TYPE & SECTION BREAKDOWN)

| Page Type (`PageTypeEnum`) | So Luong Trang | Infobox Fields Mau | Standard Headings Mau |
| :--- | :--- | :--- | :--- |
{table_str}

---

## 4. MA TRẬN QUAN HỆ THỰC THỂ WIKI (ENTITY RELATIONSHIP ER DIAGRAM)

```mermaid
{er_str}
```
"""
    return doc_content


def main() -> None:
    print("[+] Scanning Wuthering Waves Wiki data...")

    # Primary source: data/canonical/canonical.jsonl
    pages = scan_canonical_jsonl(Path("data/canonical/canonical.jsonl"))

    # Fallback/Supplemental source: data/lore & data/raw_wiki
    if not pages:
        print("[*] canonical.jsonl not found or empty, scanning raw data directories...")
        pages.extend(scan_lore_directory(Path("data/lore")))
        pages.extend(scan_lore_directory(Path("data/raw_wiki")))

    if not pages:
        print("[!] No wiki pages found! Generating default structural diagram...")

    print(f"[*] Successfully analyzed {len(pages)} Wiki pages.")

    doc_md = analyze_wiki_structure(pages)

    out_file = Path("docs/WUTHERING_WAVES_WIKI_STRUCTURE.md")
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(doc_md, encoding="utf-8")

    print(f"[SUCCESS] Wiki structure diagram exported to: {out_file}")


if __name__ == "__main__":
    main()
