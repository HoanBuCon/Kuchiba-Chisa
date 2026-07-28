"""Smoke test for PHA 1: Data Schemas."""

import json
from datetime import datetime

from app.infrastructure.ingestion.models import (
    RawPage,
    RawPageMeta,
    CanonicalPage,
    CanonicalMeta,
    CanonicalIdentity,
    CanonicalSection,
    DocumentMetadata,
    ExtractedEntity,
    EntityRelationship,
    QualityReport,
    QualityIssue,
    ProvenanceRecord,
    PageTypeEnum,
    ContentTypeEnum,
    ChunkStrategyEnum,
    Chunk,
)
from app.infrastructure.ingestion.models.chunk_model import (
    generate_chunk_id,
    compute_text_hash,
    estimate_token_count,
)


def test_raw_page():
    print("=== Test 1: RawPage ===")
    meta = RawPageMeta(
        page_id=54321,
        title="Startorch Academy",
        revision_id=789012,
        revision_timestamp=datetime(2026, 7, 20, 14, 30),
        categories=["Organizations", "Lahai-Roi", "Schools"],
        content_length_bytes=15775,
    )
    raw = RawPage(
        meta=meta,
        wikitext="'''Startorch Academy''' is a multinational school built by...",
    )
    assert raw.meta.page_id == 54321
    assert raw.meta.title == "Startorch Academy"
    assert len(raw.meta.categories) == 3
    assert raw.meta.is_redirect is False
    print(f"  page_id={raw.meta.page_id}, title={raw.meta.title}")
    print(f"  categories={raw.meta.categories}")
    print(f"  PASS\n")


def test_canonical_page():
    print("=== Test 2: CanonicalPage (full realistic record) ===")
    page = CanonicalPage(
        _meta=CanonicalMeta(
            source_revision_id=789012,
            raw_content_hash="sha256:abc123def456",
        ),
        identity=CanonicalIdentity(
            page_id=54321,
            title="Startorch Academy",
            canonical_slug="startorch_academy",
            page_type=PageTypeEnum.GENERIC,
            page_type_confidence=0.95,
        ),
        document_metadata=DocumentMetadata(
            canonical_name="Startorch Academy",
            entity_type="ORGANIZATION",
            region="Lahai-Roi",
            faction="Spacetrek Collective",
            categories=["Organizations", "Lahai-Roi", "Schools"],
        ),
        entities=[
            ExtractedEntity(name="Startorch Academy", type="ORGANIZATION", is_primary=True),
            ExtractedEntity(name="Lucilla", type="CHARACTER", role="President"),
            ExtractedEntity(name="Chisa", type="CHARACTER", role="Student"),
        ],
        relationships=[
            EntityRelationship(source="Startorch Academy", relation="LOCATED_IN", target="Lahai-Roi"),
            EntityRelationship(source="Chisa", relation="STUDENT_AT", target="Startorch Academy"),
        ],
        cross_references=["Lahai-Roi", "Spacetrek Collective", "Rabelle College"],
        sections=[
            CanonicalSection(
                section_id="54321-H2-00",
                title="Lead",
                level=1,
                content="Startorch Academy is a multinational school built by the Spacetrek Collective specifically for Resonators in Lahai-Roi.",
                content_type=ContentTypeEnum.PROSE,
                entities_in_section=["Startorch Academy", "Spacetrek Collective"],
                sources=[
                    ProvenanceRecord(origin="wiki_crawl", language="en", revision_id=789012),
                    ProvenanceRecord(origin="curated", language="vi", priority="supplement"),
                ],
            ),
            CanonicalSection(
                section_id="54321-H2-02",
                title="Members",
                level=2,
                content_type=ContentTypeEnum.HEADING_ONLY,
                subsections=[
                    CanonicalSection(
                        section_id="54321-H2-02-H3-01",
                        title="Staff",
                        level=3,
                        content_type=ContentTypeEnum.TABLE,
                        structured_data=[
                            {"Name": "Lucilla", "Position": "President"},
                            {"Name": "Mornye", "Position": "Professor"},
                        ],
                        entities_in_section=["Lucilla", "Mornye"],
                    ),
                ],
            ),
        ],
        quality=QualityReport(
            parser_confidence=0.82,
            issues=[
                QualityIssue(type="EMPTY_SECTION", location="## Descriptions", severity="MEDIUM"),
            ],
            tables_parsed=3,
            boilerplate_removed=["Other Languages", "References"],
        ),
    )

    assert page.identity.page_id == 54321
    assert page.identity.page_type == PageTypeEnum.GENERIC
    assert page.identity.page_type_confidence == 0.95
    assert len(page.entities) == 3
    assert len(page.relationships) == 2
    assert len(page.sections) == 2
    assert page.sections[1].subsections is not None
    assert len(page.sections[1].subsections) == 1
    assert page.quality.parser_confidence == 0.82
    assert page.document_metadata.region == "Lahai-Roi"

    json_size = len(page.model_dump_json())
    print(f"  identity: {page.identity.page_id} - {page.identity.title}")
    print(f"  page_type: {page.identity.page_type.value} ({page.identity.page_type_confidence})")
    print(f"  entities: {len(page.entities)}, relationships: {len(page.relationships)}")
    print(f"  sections: {len(page.sections)}, subsections: {len(page.sections[1].subsections)}")
    print(f"  provenance sources: {len(page.sections[0].sources)}")
    print(f"  quality confidence: {page.quality.parser_confidence}")
    print(f"  JSON size: {json_size} chars")
    print(f"  PASS\n")
    return page


def test_chunk():
    print("=== Test 3: Chunk with factory method ===")
    chunk = Chunk.from_text(
        page_id=54321,
        heading_path="Startorch Academy > Lead",
        chunk_index=0,
        text_content="Startorch Academy is a multinational school built by the Spacetrek Collective specifically for Resonators in Lahai-Roi.",
        page_title="Startorch Academy",
        page_type="GENERIC",
        canonical_name="Startorch Academy",
        region="Lahai-Roi",
        entities=["Startorch Academy", "Spacetrek Collective", "Lahai-Roi"],
        quality_score=0.95,
    )

    assert chunk.page_id == 54321
    assert chunk.text_hash.startswith("sha256:")
    assert chunk.token_count_approx > 0
    assert chunk.quality_score == 0.95
    assert len(chunk.entities) == 3
    assert "GENERIC" in chunk.context_prefix
    assert "Startorch Academy" in chunk.context_prefix

    print(f"  chunk_id: {chunk.chunk_id}")
    print(f"  text_hash: {chunk.text_hash[:40]}...")
    print(f"  token_count: {chunk.token_count_approx}")
    print(f"  context_prefix: {chunk.context_prefix}")
    print(f"  entities: {chunk.entities}")
    print(f"  PASS\n")
    return chunk


def test_deterministic_ids():
    print("=== Test 4: Deterministic UUIDv5 Idempotency ===")
    id1 = generate_chunk_id(54321, "Startorch Academy > Lead", 0)
    id2 = generate_chunk_id(54321, "Startorch Academy > Lead", 0)
    id3 = generate_chunk_id(54321, "Startorch Academy > Lead", 1)
    id4 = generate_chunk_id(99999, "Startorch Academy > Lead", 0)

    assert id1 == id2, "Same input must produce same ID"
    assert id1 != id3, "Different chunk_index must produce different ID"
    assert id1 != id4, "Different page_id must produce different ID"

    print(f"  Same input  -> same ID:      {id1 == id2}")
    print(f"  Diff index  -> different ID: {id1 != id3}")
    print(f"  Diff page   -> different ID: {id1 != id4}")
    print(f"  PASS\n")


def test_text_hash():
    print("=== Test 5: Text Hash ===")
    h1 = compute_text_hash("Hello World")
    h2 = compute_text_hash("Hello World")
    h3 = compute_text_hash("Hello World!")

    assert h1 == h2
    assert h1 != h3
    assert h1.startswith("sha256:")

    print(f"  Deterministic: {h1 == h2}")
    print(f"  Different text -> different hash: {h1 != h3}")
    print(f"  Format: {h1[:15]}...")
    print(f"  PASS\n")


def test_token_estimation():
    print("=== Test 6: Token Estimation ===")
    short = estimate_token_count("Hello")
    medium = estimate_token_count("Startorch Academy is a multinational school")
    long_text = "word " * 500
    long_count = estimate_token_count(long_text)

    assert short > 0
    assert medium > short
    assert long_count > medium

    print(f"  Short text: {short} tokens")
    print(f"  Medium text: {medium} tokens")
    print(f"  Long text (~500 words): {long_count} tokens")
    print(f"  PASS\n")


import pytest


@pytest.fixture
def page() -> CanonicalPage:
    return test_canonical_page()


def test_json_roundtrip(page: CanonicalPage):
    print("=== Test 7: JSON Round-trip ===")
    json_str = page.model_dump_json(by_alias=True)
    restored = CanonicalPage.model_validate_json(json_str)

    assert restored.identity.page_id == page.identity.page_id
    assert restored.identity.title == page.identity.title
    assert len(restored.sections) == len(page.sections)
    assert len(restored.entities) == len(page.entities)
    assert restored.quality.parser_confidence == page.quality.parser_confidence

    # Verify nested subsections survived
    assert restored.sections[1].subsections is not None
    assert len(restored.sections[1].subsections) == 1
    assert restored.sections[1].subsections[0].structured_data is not None

    print(f"  Identity preserved: {restored.identity.page_id == page.identity.page_id}")
    print(f"  Sections preserved: {len(restored.sections) == len(page.sections)}")
    print(f"  Nested subsections: OK")
    print(f"  Structured data: OK")
    print(f"  PASS\n")


def test_jsonl_streaming(page: CanonicalPage):
    print("=== Test 8: JSONL Streaming Simulation ===")
    # Simulate writing 3 pages to JSONL
    pages = []
    for i in range(3):
        p = page.model_copy(deep=True)
        p.identity.page_id = 54321 + i
        p.identity.title = f"Page_{i}"
        pages.append(p)

    lines = [p.model_dump_json(by_alias=True) for p in pages]
    jsonl_content = "\n".join(lines)

    # Read back
    restored_pages = []
    for line in jsonl_content.split("\n"):
        if line.strip():
            restored_pages.append(CanonicalPage.model_validate_json(line))

    assert len(restored_pages) == 3
    assert restored_pages[0].identity.page_id == 54321
    assert restored_pages[2].identity.page_id == 54323

    print(f"  Wrote {len(pages)} pages to JSONL")
    print(f"  Read back {len(restored_pages)} pages")
    print(f"  IDs: {[p.identity.page_id for p in restored_pages]}")
    print(f"  PASS\n")


def test_extra_fields_ignored():
    print("=== Test 9: Extra Fields Ignored (ConfigDict extra='ignore') ===")
    # Ensure forward compatibility - unknown fields don't crash deserialization
    data = {
        "page_id": 99999,
        "title": "Test",
        "revision_id": 1,
        "revision_timestamp": "2026-07-20T14:30:00",
        "future_field": "should be ignored",
    }
    meta = RawPageMeta.model_validate(data)
    assert meta.page_id == 99999
    assert not hasattr(meta, "future_field")
    print(f"  Unknown field silently ignored: OK")
    print(f"  PASS\n")


if __name__ == "__main__":
    test_raw_page()
    page = test_canonical_page()
    test_chunk()
    test_deterministic_ids()
    test_text_hash()
    test_token_estimation()
    test_json_roundtrip(page)
    test_jsonl_streaming(page)
    test_extra_fields_ignored()
    print("=" * 50)
    print("ALL 9 TESTS PASSED — PHA 1 COMPLETE")
    print("=" * 50)
