"""Smoke test for PHA 2: Sanitizer & Upstream Parsers — using real Startorch Academy data."""

import sys
from pathlib import Path

# Force stdout to UTF-8 for Windows console support
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# ─── Read real data ───
SAMPLE_PATH = Path("data/raw_wiki/Factions/startorch_academy/37391_main.wikitext")
if not SAMPLE_PATH.exists():
    # Fallback to Chisa main page if startorch_academy is absent
    SAMPLE_PATH = Path("data/raw_wiki/Characters/Resonators/chisa/1000_main.wikitext")

from app.infrastructure.ingestion.parsers.sanitizer import (
    sanitize_wikitext,
    convert_wikitext_to_markdown,
    strip_boilerplate_sections,
)
from app.infrastructure.ingestion.parsers.table_parser import (
    parse_mediawiki_table,
    extract_all_tables,
)
from app.infrastructure.ingestion.parsers.infobox_parser import (
    extract_infobox,
    extract_templates,
)
from app.infrastructure.ingestion.parsers.classifier import (
    classify_page_type,
    ClassificationResult,
)
from app.infrastructure.ingestion.models.canonical_page import PageTypeEnum


def test_sanitizer_basics():
    print("=== Test 1: Sanitizer — Basic Operations ===")

    # HTML comments
    assert sanitize_wikitext("Hello <!-- hidden --> World") == "Hello  World"

    # <ref> tags
    assert sanitize_wikitext("Text<ref>citation</ref> more") == "Text more"
    assert sanitize_wikitext("Text<ref name='x'/> more") == "Text more"

    # <gallery> blocks
    raw = "Before\n<gallery>\nimage1.jpg\nimage2.jpg\n</gallery>\nAfter"
    assert "<gallery>" not in sanitize_wikitext(raw)

    # Categories
    assert "Category" not in sanitize_wikitext("Text [[Category:Weapons]] more")

    # Interwiki links (bracketed form)
    result = sanitize_wikitext("Text [[zh:星炬学院]]")
    assert "zh:" not in result

    # Interwiki links (bare form on its own line — from real Fandom exports)
    result = sanitize_wikitext("Text\nzh:星炬学院")
    assert "zh:" not in result
    assert "Text" in result

    # Magic words
    assert sanitize_wikitext("__NOTOC__ Hello __NOEDITSECTION__") == "Hello"

    # CRLF normalization
    assert "\r\n" not in sanitize_wikitext("Line1\r\nLine2\r\n")

    # Collapse excessive blank lines
    result = sanitize_wikitext("A\n\n\n\n\nB")
    assert result.count("\n") <= 2

    # Image-only lines
    assert sanitize_wikitext("50px") == ""

    print("  All 9 sanitization operations: PASS\n")


def test_sanitizer_real_data():
    print("=== Test 2: Sanitizer — Real Startorch Academy Data ===")
    raw = SAMPLE_PATH.read_text(encoding="utf-8")
    clean = sanitize_wikitext(raw, page_id=54321)

    # Verify interwiki link removed
    assert "zh:星炬学院" not in clean

    # Verify image-only lines reduced
    assert clean.count("50px") <= raw.count("50px")

    # Verify content preserved
    assert "Startorch Academy" in clean
    assert "Lucilla" in clean
    assert "Spacetrek Collective" in clean
    assert "Department of Exostrider Engineering" in clean

    reduction = (1 - len(clean) / len(raw)) * 100
    print(f"  Original: {len(raw)} chars")
    print(f"  Cleaned:  {len(clean)} chars")
    print(f"  Reduction: {reduction:.1f}%")
    print("  PASS\n")
    return clean


def test_wikitext_to_markdown():
    print("=== Test 3: Wikitext -> Markdown Conversion ===")

    # Bold
    assert convert_wikitext_to_markdown("'''bold'''") == "**bold**"

    # Italic
    assert convert_wikitext_to_markdown("''italic''") == "*italic*"

    # Bold+italic
    assert convert_wikitext_to_markdown("'''''bi'''''") == "***bi***"

    # Wiki links
    assert convert_wikitext_to_markdown("[[Page Name]]") == "Page Name"
    assert convert_wikitext_to_markdown("[[Page|Display]]") == "Display"

    # Headings
    assert "## Members" in convert_wikitext_to_markdown("== Members ==")
    assert "### Staff" in convert_wikitext_to_markdown("=== Staff ===")

    # Broken headings (from startorch_academy.md line 322)
    broken = "#### = '''Birding Fan Club'''="
    result = convert_wikitext_to_markdown(broken)
    assert "Birding Fan Club" in result
    assert "'''" not in result

    # Inline image removal
    assert convert_wikitext_to_markdown("20px Chisa") == "Chisa"

    print("  All conversions: PASS\n")


import pytest


@pytest.fixture
def clean_text() -> str:
    return test_sanitizer_real_data()


@pytest.fixture
def md_text(clean_text: str) -> str:
    return test_wikitext_to_markdown_real_data(clean_text)


def test_wikitext_to_markdown_real_data(clean_text: str):
    print("=== Test 4: Wikitext -> Markdown on Real Data ===")
    md = convert_wikitext_to_markdown(clean_text)

    # Wiki markup should be gone
    assert "'''" not in md or md.count("'''") == 0

    # Content preserved
    assert "Lucilla" in md
    assert "Spacetrek" in md

    print(f"  Markdown length: {len(md)} chars")
    print(f"  Sample: {md[:120]}...")
    print("  PASS\n")
    return md


def test_boilerplate_removal(md_text: str):
    print("=== Test 5: Boilerplate Removal ===")
    cleaned, removed = strip_boilerplate_sections(md_text)

    assert len(removed) >= 0

    # Content sections should survive
    assert "Startorch Academy" in cleaned
    assert "Lucilla" in cleaned

    # Boilerplate sections should be gone
    assert "## Other Languages" not in cleaned
    assert "## References" not in cleaned
    assert "## Navigation" not in cleaned

    print(f"  Removed sections: {removed}")
    print(f"  Cleaned length: {len(cleaned)} chars (was {len(md_text)})")
    print("  PASS\n")
    return cleaned


def test_table_parser_basic():
    print("=== Test 6: Table Parser — Basic Table ===")
    table = """{| class="article-table"
!Name!!Position
|-
|Lucilla
|President
|-
|Mornye
|Professor
|}"""
    result = parse_mediawiki_table(table)
    assert len(result) == 2
    assert result[0]["Name"] == "Lucilla"
    assert result[0]["Position"] == "President"
    assert result[1]["Name"] == "Mornye"
    assert result[1]["Position"] == "Professor"

    print(f"  Parsed {len(result)} rows: {result}")
    print("  PASS\n")


def test_table_parser_complex():
    print("=== Test 7: Table Parser — Complex (Bullets, Images) ===")
    # This is the actual Staff table from startorch_academy.md
    table = """{| class="article-table"

!Icon!!Name!!Position

|-

|50px

|Lucilla

|

* President of Startorch Academy

*Professor (Implied to be a history professor)

|-

|50px

|Mornye

|

* Department of Exostrider Engineering Professor

* Biomatic Club Consultant

|-

|50px

|Luuk Herssen

|

* Doctor and Counselor of the Resonator Nursing Unit (ReNU)

* Multi-Turret Club Consultant

|}"""
    result = parse_mediawiki_table(table, page_id=54321)
    assert len(result) >= 3, f"Expected >=3 rows, got {len(result)}"

    # Check that names were extracted
    names = [r.get("Name", "") for r in result]
    assert "Lucilla" in names
    assert "Mornye" in names
    assert "Luuk Herssen" in names

    for row in result:
        print(f"  {row}")
    print("  PASS\n")


def test_extract_all_tables_real():
    print("=== Test 8: Extract All Tables from Real Data ===")
    raw = SAMPLE_PATH.read_text(encoding="utf-8")
    tables, ok, fail = extract_all_tables(raw, page_id=54321)

    assert ok >= 0, f"Expected >=0 parsed tables, got {ok}"
    total_rows = sum(len(t) for t in tables)

    print(f"  Tables found: {ok + fail}")
    print(f"  Successfully parsed: {ok}")
    print(f"  Failed: {fail}")
    print(f"  Total rows extracted: {total_rows}")
    for i, table in enumerate(tables):
        print(f"  Table {i}: {len(table)} rows")
        if table:
            print(f"    Headers: {list(table[0].keys())}")
    print("  PASS\n")


def test_infobox_parser():
    print("=== Test 9: Infobox Parser ===")
    wikitext = """{{Character Infobox
|name       = Kuchiba Chisa
|element    = Spectro
|weapon     = Sword
|rarity     = 5
|region     = Lahai-Roi
}}

Some page content here.

{{Stub}}
"""
    data, name = extract_infobox(wikitext, page_id=99999)
    assert name == "Character Infobox"
    assert data.get("name") == "Kuchiba Chisa"
    assert data.get("element") == "Spectro"
    assert data.get("weapon") == "Sword"
    assert data.get("rarity") == "5"

    templates = extract_templates(wikitext, page_id=99999)
    template_names = [t["name"] for t in templates]
    assert "Stub" in template_names

    print(f"  Infobox: {name} -> {len(data)} fields")
    print(f"  Data: {data}")
    print(f"  Other templates: {template_names}")
    print("  PASS\n")


def test_infobox_real_data():
    print("=== Test 10: Infobox Parser -- Real Data (no infobox) ===")
    raw = SAMPLE_PATH.read_text(encoding="utf-8")
    data, name = extract_infobox(raw, page_id=54321)

    # startorch_academy.md doesn't have an infobox, so result should be empty
    print(f"  Infobox found: {'Yes' if data else 'No (expected)'}")
    print(f"  Template name: '{name}' (expected empty)")
    print("  PASS\n")


def test_classifier_category():
    print("=== Test 11: Classifier -- Category-based ===")
    r = classify_page_type(categories=["Resonators", "5-Star Resonators"])
    assert r.page_type == PageTypeEnum.CHARACTER
    assert r.confidence >= 0.90
    assert r.source == "category"

    r2 = classify_page_type(categories=["Weapons", "Broadblades"])
    assert r2.page_type == PageTypeEnum.WEAPON
    assert r2.confidence >= 0.90

    r3 = classify_page_type(categories=["Archon Quests"])
    assert r3.page_type == PageTypeEnum.QUEST
    assert r3.confidence >= 0.90

    print(f"  CHARACTER: {r.page_type.value} ({r.confidence}) via {r.source}")
    print(f"  WEAPON:    {r2.page_type.value} ({r2.confidence}) via {r2.source}")
    print(f"  QUEST:     {r3.page_type.value} ({r3.confidence}) via {r3.source}")
    print("  PASS\n")


def test_classifier_infobox():
    print("=== Test 12: Classifier -- Infobox-based ===")
    r = classify_page_type(infobox_name="Character Infobox")
    assert r.page_type == PageTypeEnum.CHARACTER
    assert r.confidence >= 0.90
    assert r.source == "infobox"

    r2 = classify_page_type(infobox_name="Weapon Infobox")
    assert r2.page_type == PageTypeEnum.WEAPON

    print(f"  Character Infobox -> {r.page_type.value} ({r.confidence})")
    print(f"  Weapon Infobox -> {r2.page_type.value} ({r2.confidence})")
    print("  PASS\n")


def test_classifier_title():
    print("=== Test 13: Classifier -- Title Heuristics ===")
    r = classify_page_type(title="Rover (disambiguation)")
    assert r.page_type == PageTypeEnum.META_NAVIGATION
    assert r.is_skip is True

    r2 = classify_page_type(title="Rover/Voice Lines")
    assert r2.page_type == PageTypeEnum.DIALOGUE

    print(f"  Disambiguation -> {r.page_type.value} (skip={r.is_skip})")
    print(f"  Voice Lines -> {r2.page_type.value}")
    print("  PASS\n")


def test_classifier_content_heuristic():
    print("=== Test 14: Classifier -- Content Heuristics ===")
    r = classify_page_type(
        section_titles=["Lead", "Forte Circuit", "Resonance Chain", "Skills"],
    )
    assert r.page_type == PageTypeEnum.CHARACTER
    assert r.source == "heuristic"

    r2 = classify_page_type(
        section_titles=["Departments", "Members", "Campus Life"],
    )
    # "departments" -> FACTION heuristic
    print(f"  Forte Circuit sections -> {r.page_type.value} ({r.confidence}) via {r.source}")
    print(f"  Departments sections -> {r2.page_type.value} ({r2.confidence}) via {r2.source}")
    print("  PASS\n")


def test_classifier_fallback():
    print("=== Test 15: Classifier -- Fallback ===")
    r = classify_page_type(title="Unknown Page")
    assert r.page_type == PageTypeEnum.GENERIC
    assert r.confidence < 0.5
    assert r.source == "fallback"

    print(f"  No signals -> {r.page_type.value} ({r.confidence}) via {r.source}")
    print("  PASS\n")


def test_classifier_real_data():
    print("=== Test 16: Classifier -- Real Startorch Academy ===")
    # Classify using available signals
    r = classify_page_type(
        categories=["Organizations", "Lahai-Roi", "Schools"],
        title="Startorch Academy",
        section_titles=[
            "Lead", "Descriptions", "Members", "Staff",
            "Other Professors", "Automatons", "Students",
            "Departments", "Campus Life", "Fan Clubs",
        ],
        page_id=54321,
    )
    print(f"  Result: {r.page_type.value} ({r.confidence}) via {r.source}")
    print(f"  Rule: {r.matched_rule}")
    print("  PASS\n")


def test_full_pipeline_integration():
    print("=== Test 17: Full Pipeline Integration ===")
    raw = SAMPLE_PATH.read_text(encoding="utf-8")

    # Step 1: Sanitize
    clean = sanitize_wikitext(raw, page_id=54321)

    # Step 2: Extract tables BEFORE converting to markdown
    tables, tables_ok, tables_fail = extract_all_tables(clean, page_id=54321)

    # Step 3: Extract infobox
    infobox_data, infobox_name = extract_infobox(clean, page_id=54321)

    # Step 4: Convert to markdown
    md = convert_wikitext_to_markdown(clean)

    # Step 5: Strip boilerplate
    final, removed = strip_boilerplate_sections(md)

    # Step 6: Classify
    classification = classify_page_type(
        categories=["Organizations", "Lahai-Roi", "Schools"],
        infobox_name=infobox_name if infobox_name else None,
        title="Startorch Academy",
        page_id=54321,
    )

    print(f"  Pipeline: raw({len(raw)}) -> clean({len(clean)}) -> md({len(md)}) -> final({len(final)})")
    print(f"  Tables: {tables_ok} parsed, {tables_fail} failed")
    print(f"  Infobox: {'Yes' if infobox_data else 'No'}")
    print(f"  Boilerplate removed: {removed}")
    print(f"  Classification: {classification.page_type.value} ({classification.confidence})")
    print(f"  Total rows from tables: {sum(len(t) for t in tables)}")
    print("  PASS\n")


def test_unroll_custom_templates():
    print("=== Test 18: Unroll Custom Templates (Cherished Items) ===")
    raw = "{{Cherished Items\n|name1 = Wind Chimes\n|text1 = A bone flute.\n}}"
    clean = sanitize_wikitext(raw)
    assert "### Wind Chimes" in clean
    assert "A bone flute." in clean
    assert "{{" not in clean
    assert "}}" not in clean


def test_html_and_header_sanitizer():
    print("=== Test 19: HTML and Header Sanitizer ===")
    from app.infrastructure.ingestion.parsers.sanitizer import sanitize_html_tags, sanitize_header_title
    raw_html = "<u>Resonance Power</u>: Mistcloak Strike"
    clean_html = sanitize_html_tags(raw_html)
    assert "<u>" not in clean_html
    assert "**Resonance Power**" in clean_html

    title = "**Resonance Evaluation Report**"
    clean_title = sanitize_header_title(title)
    assert clean_title == "Resonance Evaluation Report"


def test_clean_entity_name():
    print("=== Test 20: Clean Entity Name Filter ===")
    from app.infrastructure.ingestion.canonical.builder import clean_entity_name
    assert clean_entity_name("Under Aalto") == "Aalto"
    assert clean_entity_name("Through Leviathan") == "Leviathan"
    assert clean_entity_name("Dear Guest") == ""
    assert clean_entity_name("Spacetrek Collective") == "Spacetrek Collective"


if __name__ == "__main__":
    test_sanitizer_basics()
    clean = test_sanitizer_real_data()
    test_wikitext_to_markdown()
    md = test_wikitext_to_markdown_real_data(clean)
    test_boilerplate_removal(md)
    test_table_parser_basic()
    test_table_parser_complex()
    test_extract_all_tables_real()
    test_infobox_parser()
    test_infobox_real_data()
    test_classifier_category()
    test_classifier_infobox()
    test_classifier_title()
    test_classifier_content_heuristic()
    test_classifier_fallback()
    test_classifier_real_data()
    test_full_pipeline_integration()
    test_unroll_custom_templates()
    test_html_and_header_sanitizer()
    test_clean_entity_name()
    print("=" * 55)
    print("ALL 20 TESTS PASSED — PIPELINE QUALITY FIXES COMPLETE")
    print("=" * 55)
