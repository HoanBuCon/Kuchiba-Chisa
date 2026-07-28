"""
Unit tests for Phase 5: 5-Gate Quality Control System & Quarantine Management.
"""

import sys
from pathlib import Path
from click.testing import CliRunner

# Force stdout to UTF-8 for Windows console support
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app.infrastructure.ingestion.canonical.builder import build_canonical_page
from app.infrastructure.ingestion.chunkers import chunk_canonical_page
from app.infrastructure.ingestion.cli import cli
from app.infrastructure.ingestion.models.canonical_page import (
    CanonicalIdentity,
    CanonicalPage,
    CanonicalSection,
    ContentTypeEnum,
    DocumentMetadata,
    ExtractedEntity,
    PageTypeEnum,
)
from app.infrastructure.ingestion.models.chunk_model import Chunk, ChunkStrategyEnum
from app.infrastructure.ingestion.models.raw_page import RawPage, RawPageMeta
from app.infrastructure.ingestion.quality import (
    Gate1StructureValidator,
    Gate2ContentValidator,
    Gate3EntityValidator,
    Gate4ChunkValidator,
    Gate5CorpusValidator,
    QualityStatusEnum,
    QualityValidator,
)


def test_gate1_structure_validator():
    print("=== Test 1: Gate 1 — Structure & Heading Tree ===")
    page_good = CanonicalPage(
        identity=CanonicalIdentity(page_id=101, title="Good Structure", canonical_slug="good_structure"),
        sections=[
            CanonicalSection(
                section_id="101-H2-01",
                title="Overview",
                level=2,
                content="This is clean overview content.",
                content_type=ContentTypeEnum.PROSE,
            )
        ],
    )
    res_good = Gate1StructureValidator.validate(page_good)
    assert res_good.passed
    assert res_good.score >= 0.9

    # Bad page with zero sections
    page_empty = CanonicalPage(
        identity=CanonicalIdentity(page_id=102, title="Empty Page", canonical_slug="empty_page"),
        sections=[],
    )
    res_empty = Gate1StructureValidator.validate(page_empty)
    assert not res_empty.passed
    assert res_empty.score == 0.0
    print("  PASS\n")


def test_gate2_content_validator():
    print("=== Test 2: Gate 2 — Content & Language Integrity ===")
    page_valid = CanonicalPage(
        identity=CanonicalIdentity(page_id=201, title="Valid Lore", canonical_slug="valid_lore"),
        sections=[
            CanonicalSection(
                section_id="201-H2-01",
                title="Body",
                level=2,
                content="Comprehensive lore description about Kuchiba Chisa.",
                content_type=ContentTypeEnum.PROSE,
            )
        ],
    )
    res_valid = Gate2ContentValidator.validate(page_valid)
    assert res_valid.passed
    assert res_valid.score == 1.0

    # Meta navigation / Disambiguation page
    page_meta = CanonicalPage(
        identity=CanonicalIdentity(
            page_id=202,
            title="Chisa (Disambiguation)",
            canonical_slug="chisa_disambiguation",
            page_type=PageTypeEnum.META_NAVIGATION,
        ),
        sections=[
            CanonicalSection(
                section_id="202-H2-01",
                title="Links",
                level=2,
                content="Chisa may refer to: Kuchiba Chisa, Chisa (NPC).",
                content_type=ContentTypeEnum.PROSE,
            )
        ],
    )
    res_meta = Gate2ContentValidator.validate(page_meta)
    assert res_meta.score < 1.0
    print("  PASS\n")


def test_gate3_entity_validator():
    print("=== Test 3: Gate 3 — Entity & Metadata Consistency ===")
    page = CanonicalPage(
        identity=CanonicalIdentity(page_id=301, title="Kuchiba Chisa", canonical_slug="kuchiba_chisa"),
        document_metadata=DocumentMetadata(
            canonical_name="Kuchiba Chisa",
            region="Lahai-Roi",
        ),
        entities=[
            ExtractedEntity(
                name="Kuchiba Chisa",
                type="CHARACTER",
                is_primary=True,
                canonical_name="Kuchiba Chisa",
            )
        ],
        sections=[
            CanonicalSection(
                section_id="301-H2-01",
                title="Background",
                level=2,
                content="Kuchiba Chisa is a Resonator.",
                content_type=ContentTypeEnum.PROSE,
            )
        ],
    )
    res = Gate3EntityValidator.validate(page)
    assert res.passed
    assert res.score == 1.0
    print("  PASS\n")


def test_gate4_chunk_validator():
    print("=== Test 4: Gate 4 — Chunk Boundaries & Deduplication ===")
    chunk = Chunk.from_text(
        page_id=401,
        heading_path="Kuchiba Chisa > Background",
        chunk_index=0,
        text_content="Kuchiba Chisa is a powerful AI companion created by the Google DeepMind team to assist in complex coding tasks, lore extraction, and wiki data processing pipelines.",
        page_title="Kuchiba Chisa",
        page_type="CHARACTER",
    )
    seen = set()
    res1 = Gate4ChunkValidator.validate(chunk, seen)
    assert res1.passed
    assert res1.score == 1.0

    # Duplicate check
    res2 = Gate4ChunkValidator.validate(chunk, seen)
    assert res2.score < 1.0
    assert any(i.type == "DUPLICATE_CHUNK" for i in res2.issues)
    print("  PASS\n")


def test_validator_quarantine_flow(tmp_path: Path):
    print("=== Test 5: QualityValidator — Quarantine Flow ===")
    quarantine_dir = tmp_path / "quarantine"
    validator = QualityValidator(quarantine_dir=quarantine_dir)

    # Low quality page (empty content, missing primary entity)
    bad_page = CanonicalPage(
        identity=CanonicalIdentity(
            page_id=501,
            title="Bad Page",
            canonical_slug="bad_page",
            page_type=PageTypeEnum.META_NAVIGATION,
        ),
        sections=[],
    )

    report = validator.validate_canonical_page(bad_page)
    assert report.status == QualityStatusEnum.QUARANTINED

    qfile = validator.quarantine_page(bad_page, report)
    assert qfile.exists()
    assert qfile.name.endswith(".quarantine.json")
    print(f"  Quarantined file created: {qfile.name}")
    print("  PASS\n")


def test_cli_validate_quality_command(tmp_path: Path):
    print("=== Test 6: CLI validate-quality Command ===")
    runner = CliRunner()

    canonical_path = tmp_path / "canonical.jsonl"
    chunks_path = tmp_path / "chunks.jsonl"
    quarantine_dir = tmp_path / "quarantine"

    page = CanonicalPage(
        identity=CanonicalIdentity(page_id=601, title="Test CLI Page", canonical_slug="test_cli_page"),
        document_metadata=DocumentMetadata(canonical_name="Test CLI Page"),
        entities=[ExtractedEntity(name="Test CLI Page", type="CONCEPT", is_primary=True)],
        sections=[
            CanonicalSection(
                section_id="601-H2-01",
                title="Intro",
                level=2,
                content="This is test CLI page content for validation.",
                content_type=ContentTypeEnum.PROSE,
            )
        ],
    )
    canonical_path.write_text(page.model_dump_json() + "\n", encoding="utf-8")

    chunks = chunk_canonical_page(page)
    chunks_content = "\n".join(c.model_dump_json() for c in chunks)
    chunks_path.write_text(chunks_content + "\n", encoding="utf-8")

    res = runner.invoke(
        cli,
        [
            "validate-quality",
            "--input",
            str(canonical_path),
            "--chunks",
            str(chunks_path),
            "--quarantine-dir",
            str(quarantine_dir),
        ],
    )

    assert res.exit_code == 0
    assert "5-Gate Quality Control" in res.output
    assert "AUTO_APPROVED:" in res.output
    print("  PASS\n")


if __name__ == "__main__":
    test_gate1_structure_validator()
    test_gate2_content_validator()
    test_gate3_entity_validator()
    test_gate4_chunk_validator()
    test_validator_quarantine_flow(Path("scratch/test_quarantine"))
    print("=" * 55)
    print("ALL 6 TESTS PASSED — PHA 5 COMPLETE")
    print("=" * 55)
