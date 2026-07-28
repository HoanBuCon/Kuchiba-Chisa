"""Smoke test for PHA 4: Structure-Aware Chunkers."""

import sys
from datetime import datetime
from pathlib import Path

# Force stdout to UTF-8 for Windows console support
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

SAMPLE_PATH = Path(r"d:\Hoc_Tap\Code\Du_An_Ca_Nhan\Chisa_bot\kuchiba_chisa\data\lore\world_lore\startorch_academy.md")

from app.infrastructure.ingestion.canonical.builder import build_canonical_page
from app.infrastructure.ingestion.chunkers import (
    DialogueChunker,
    GenericChunker,
    TableInlinerChunker,
    chunk_canonical_page,
)
from app.infrastructure.ingestion.models.canonical_page import (
    CanonicalIdentity,
    CanonicalPage,
    CanonicalSection,
    ContentTypeEnum,
    DocumentMetadata,
    PageTypeEnum,
)
from app.infrastructure.ingestion.models.chunk_model import ChunkStrategyEnum, Chunk, generate_chunk_id
from app.infrastructure.ingestion.models.raw_page import RawPage, RawPageMeta


def test_generic_chunker_basic():
    print("=== Test 1: GenericChunker — Paragraph Merge & Overlap ===")
    page = CanonicalPage(
        identity=CanonicalIdentity(
            page_id=1,
            title="Startorch Overview",
            canonical_slug="startorch_overview",
            page_type=PageTypeEnum.REGION,
        ),
        document_metadata=DocumentMetadata(
            canonical_name="Startorch Academy",
            region="Lahai-Roi",
        ),
    )

    section = CanonicalSection(
        section_id="1-H2-01",
        title="Academy Life",
        level=2,
        content="Paragraph 1: Startorch Academy is a multinational school in Lahai-Roi.\n\nParagraph 2: Students take cross-disciplinary courses in foundational sciences and humanities.\n\nParagraph 3: ReNU offers medical care and Frequency Modulation therapy.",
        content_type=ContentTypeEnum.PROSE,
        entities_in_section=["Startorch Academy", "Lahai-Roi"],
    )

    chunker = GenericChunker(target_token_size=30, max_token_size=60, overlap_sentences=1)
    chunks = chunker.chunk_section(page, section, "Startorch Overview > Academy Life")

    assert len(chunks) >= 1
    for c in chunks:
        assert c.page_title == "Startorch Overview"
        assert c.canonical_name == "Startorch Academy"
        assert c.region == "Lahai-Roi"
        assert c.text_hash.startswith("sha256:")
        assert c.chunk_strategy in (ChunkStrategyEnum.PARAGRAPH_MERGE, ChunkStrategyEnum.SLIDING_WINDOW)
        assert "[REGION: Startorch Overview | Section: Startorch Overview > Academy Life]" in c.context_prefix

    print(f"  Chunks created: {len(chunks)}")
    print(f"  Chunk 0 context_prefix: {chunks[0].context_prefix}")
    print(f"  Chunk 0 tokens: {chunks[0].token_count_approx}")
    print("  PASS\n")


def test_table_inliner_chunker():
    print("=== Test 2: TableInlinerChunker — Row-to-Prose Inlining ===")
    page = CanonicalPage(
        identity=CanonicalIdentity(
            page_id=2,
            title="Startorch Staff",
            canonical_slug="startorch_staff",
            page_type=PageTypeEnum.FACTION,
        ),
        document_metadata=DocumentMetadata(
            canonical_name="Startorch Staff",
            faction="Spacetrek Collective",
        ),
    )

    section = CanonicalSection(
        section_id="2-H2-01",
        title="Staff Members",
        level=2,
        content="",
        content_type=ContentTypeEnum.TABLE,
        structured_data=[
            {"Name": "Lucilla", "Position": "President of Startorch Academy"},
            {"Name": "Mornye", "Position": "Department of Exostrider Engineering Professor"},
            {"Name": "Luuk Herssen", "Position": "Doctor and Counselor of the ReNU"},
        ],
        entities_in_section=["Lucilla", "Mornye", "Luuk Herssen"],
    )

    chunker = TableInlinerChunker(target_token_size=40, max_token_size=80)
    chunks = chunker.chunk_section(page, section, "Startorch Staff > Staff Members")

    assert len(chunks) >= 1
    all_chunk_text = "\n".join([c.text_content for c in chunks])

    for c in chunks:
        assert c.chunk_strategy == ChunkStrategyEnum.TABLE_INLINE
        assert c.content_type == "TABLE"
        assert "Name:" in c.text_content

    assert "Lucilla" in all_chunk_text
    assert "Mornye" in all_chunk_text
    assert "Luuk Herssen" in all_chunk_text

    print(f"  Chunks created: {len(chunks)}")
    print(f"  Inlined content preview: {chunks[0].text_content[:100]}...")
    print(f"  Entities in chunk 0: {chunks[0].entities}")
    print("  PASS\n")


def test_dialogue_chunker():
    print("=== Test 3: DialogueChunker — Scene Boundary & Speakers ===")
    page = CanonicalPage(
        identity=CanonicalIdentity(
            page_id=3,
            title="Ode to the Second Sunrise",
            canonical_slug="ode_to_second_sunrise",
            page_type=PageTypeEnum.QUEST,
        ),
        document_metadata=DocumentMetadata(
            canonical_name="Ode to the Second Sunrise",
            region="Lahai-Roi",
        ),
    )

    section = CanonicalSection(
        section_id="3-H2-01",
        title="Lucilla's Office Scene",
        level=2,
        content="""Rover: "Professor Lucilla, about the incident at the Research Institute..."
Lucilla: "I've been expecting you. What Warren did was unforgivable."
Rover: "We need to secure the Exostrider Engineering records."
Lucilla: "Agreed. Take this access card to the Exo Genesis Labs."
""",
        content_type=ContentTypeEnum.DIALOGUE,
        entities_in_section=["Rover", "Lucilla", "Warren"],
    )

    chunker = DialogueChunker(target_token_size=50, max_token_size=100)
    chunks = chunker.chunk_section(page, section, "Ode to the Second Sunrise > Lucilla's Office")

    assert len(chunks) >= 1
    all_dialogue_text = "\n".join([c.text_content for c in chunks])

    for c in chunks:
        assert c.chunk_strategy == ChunkStrategyEnum.SCENE_BOUNDARY
        assert c.content_type == "DIALOGUE"

    assert "Rover:" in all_dialogue_text
    assert "Lucilla:" in all_dialogue_text

    print(f"  Chunks created: {len(chunks)}")
    print(f"  Scene chunk preview:\n{chunks[0].text_content}")
    print(f"  Entities: {chunks[0].entities}")
    print("  PASS\n")


def test_full_canonical_page_chunking_real_data():
    print("=== Test 4: Full CanonicalPage Chunking on Real Data ===")
    raw_text = SAMPLE_PATH.read_text(encoding="utf-8")

    meta = RawPageMeta(
        page_id=54321,
        title="Startorch Academy",
        revision_id=789012,
        revision_timestamp=datetime(2026, 7, 20, 14, 30),
        categories=["Organizations", "Lahai-Roi", "Schools"],
    )
    raw_page = RawPage(meta=meta, wikitext=raw_text)

    # Step 1: Build CanonicalPage
    canonical = build_canonical_page(raw_page)

    # Step 2: Route through chunk_canonical_page
    chunks = chunk_canonical_page(
        canonical,
        target_token_size=200,
        max_token_size=400,
        overlap_sentences=1,
    )

    assert len(chunks) > 0, "Should generate chunks from 38 sections"

    # Verify deterministic UUIDv5 idempotency on all generated chunks
    for i, c in enumerate(chunks):
        expected_id = generate_chunk_id(c.page_id, c.heading_path, c.chunk_index)
        assert c.chunk_id == expected_id, f"Chunk {i} ID mismatch!"
        assert c.page_id == 54321
        assert c.page_title == "Startorch Academy"
        assert c.text_hash.startswith("sha256:")
        assert c.token_count_approx > 0

    # Count chunk strategies applied
    strategies = {}
    for c in chunks:
        strategies[c.chunk_strategy.value] = strategies.get(c.chunk_strategy.value, 0) + 1

    print(f"  Total Chunks Generated: {len(chunks)}")
    print(f"  Strategy Breakdown: {strategies}")
    print(f"  Chunk 0 context_prefix: {chunks[0].context_prefix}")
    print(f"  Chunk 0 token_count: {chunks[0].token_count_approx}")
    print(f"  Deterministic UUIDv5 Idempotency: ALL {len(chunks)} CHUNKS VERIFIED")
    print("  PASS\n")


def test_atomic_chunker():
    print("=== Test 5: Atomic Section Chunking ===")
    section = CanonicalSection(
        section_id="5-H2-01",
        title="Formula & Ratios",
        level=2,
        content="Spectro DMG = Base_ATK * (1 + Spectro_Bonus) * Skill_Multiplier_280%",
        content_type=ContentTypeEnum.ATOMIC,
        entities_in_section=["Spectro DMG", "Base_ATK"],
    )

    page = CanonicalPage(
        identity=CanonicalIdentity(
            page_id=5,
            title="Thread Weave Formula",
            canonical_slug="thread_weave_formula",
            page_type=PageTypeEnum.MECHANIC,
        ),
        document_metadata=DocumentMetadata(
            canonical_name="Thread Weave Formula",
        ),
        sections=[section],
    )

    chunks = chunk_canonical_page(page)

    assert len(chunks) == 1
    assert chunks[0].chunk_strategy == ChunkStrategyEnum.ATOMIC
    assert chunks[0].text_content == "Spectro DMG = Base_ATK * (1 + Spectro_Bonus) * Skill_Multiplier_280%"
    assert "[MECHANIC: Thread Weave Formula | Section: Thread Weave Formula > Formula & Ratios]" in chunks[0].context_prefix

    print(f"  Atomic chunk created: {chunks[0].chunk_strategy.value}")
    print(f"  Content: {chunks[0].text_content}")
    print("  PASS\n")


if __name__ == "__main__":
    test_generic_chunker_basic()
    test_table_inliner_chunker()
    test_dialogue_chunker()
    test_full_canonical_page_chunking_real_data()
    test_atomic_chunker()
    print("=" * 55)
    print("ALL 5 TESTS PASSED — PHA 4 COMPLETE")
    print("=" * 55)
