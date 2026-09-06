"""ING-01 fixture parity and legacy-retirement evidence."""

from __future__ import annotations

import importlib.util
import re
import uuid
from pathlib import Path

import pytest

from app.application.ingestion.stages.parent_builder_stage import (
    ParentBuilderInput,
    ParentBuilderStage,
)
from app.application.ingestion.stages.parser_stage import ParserInput, ParserStage
from app.application.ingestion.stages.semantic_chunk_builder_stage import (
    SemanticChunkBuilderInput,
    SemanticChunkBuilderStage,
)
from app.domain.entities.wiki import DownloadedPage
from app.domain.models.evidence import EvidenceAccess
from app.infrastructure.ingestion.canonical.builder import build_canonical_page
from app.infrastructure.ingestion.chunkers import chunk_canonical_page
from app.infrastructure.ingestion.models.raw_page import RawPage, RawPageMeta

SOURCE_ID = uuid.UUID("c7ad47e2-41a1-5a88-8a88-bc3c0b9c0638")
CORPUS_VERSION = "v20260906"
FIXTURE_WIKITEXT = """{{Infobox character
| name = Aalto
| affiliation = Black Shores
}}

'''Aalto''' is an information broker from the New Federation.

==Background==
Aalto serves as a Consultant of the Black Shores.

==Relationships==
Aalto works with Encore on intelligence gathering.
"""
REQUIRED_FACTS = (
    "Aalto is an information broker from the New Federation.",
    "Aalto serves as a Consultant of the Black Shores.",
    "Aalto works with Encore on intelligence gathering.",
)


class _RawStorage:
    async def read_raw_page(self, file_path: str) -> str:
        assert file_path == "fixture/aalto.wikitext"
        return FIXTURE_WIKITEXT


class _JobRepository:
    def __init__(self) -> None:
        self.events: list[tuple[uuid.UUID, str, dict[str, object]]] = []

    async def log_event(
        self,
        job_id: uuid.UUID,
        event_type: str,
        details: dict[str, object],
    ) -> None:
        self.events.append((job_id, event_type, details))


async def _canonical_application_units():
    jobs = _JobRepository()
    job_id = uuid.uuid4()
    parsed = (
        await ParserStage(raw_storage=_RawStorage(), job_repo=jobs).execute(
            job_id,
            ParserInput(
                downloaded_pages=[
                    DownloadedPage(
                        page_id=585,
                        title="Aalto",
                        revision_id=101912,
                        file_path="fixture/aalto.wikitext",
                    )
                ]
            ),
        )
    ).output
    parents = (
        await ParentBuilderStage(job_repo=jobs).execute(
            job_id,
            ParentBuilderInput(
                parsed_page=parsed[0],
                corpus_version=CORPUS_VERSION,
                source_id=SOURCE_ID,
                access=EvidenceAccess(scope="public"),
            ),
        )
    ).output
    chunks = (
        await SemanticChunkBuilderStage(job_repo=jobs).execute(
            job_id,
            SemanticChunkBuilderInput(parents=parents),
        )
    ).output
    return parsed[0], parents, chunks


@pytest.mark.asyncio
async def test_fact_fixture_preserves_revision_and_content_across_both_paths() -> None:
    """Prove factual parity before retiring the legacy composition root."""

    parsed, parents, chunks = await _canonical_application_units()
    legacy_page = build_canonical_page(
        RawPage(
            meta=RawPageMeta(
                page_id=585,
                title="Aalto",
                revision_id=101912,
                categories=["Resonators"],
            ),
            wikitext=FIXTURE_WIKITEXT,
        )
    )
    legacy_chunks = chunk_canonical_page(legacy_page)

    application_text = "\n".join(parent.markdown for parent in parents)
    legacy_text = "\n".join(chunk.text_content for chunk in legacy_chunks)
    for fact in REQUIRED_FACTS:
        assert fact in application_text
        assert fact in re.sub(r"[*_`]", "", legacy_text)

    assert parsed.page_id == legacy_page.identity.page_id == 585
    assert parsed.revision_id == legacy_page.meta.source_revision_id == 101912
    assert chunks
    assert legacy_chunks


@pytest.mark.asyncio
async def test_canonical_units_add_required_provenance_acl_spans_and_stable_ids() -> None:
    first_page, first_parents, first_chunks = await _canonical_application_units()
    second_page, second_parents, second_chunks = await _canonical_application_units()

    assert first_page == second_page
    assert [parent.id for parent in first_parents] == [
        parent.id for parent in second_parents
    ]
    assert [chunk.chunk_id for chunk in first_chunks] == [
        chunk.chunk_id for chunk in second_chunks
    ]
    assert {parent.source_id for parent in first_parents} == {SOURCE_ID}
    assert {parent.corpus_version for parent in first_parents} == {CORPUS_VERSION}
    assert {parent.access for parent in first_parents} == {
        EvidenceAccess(scope="public")
    }
    for chunk in first_chunks:
        parent = next(parent for parent in first_parents if parent.id == chunk.parent_id)
        start = int(chunk.metadata["chunk_start_offset"])
        end = int(chunk.metadata["chunk_end_offset"])
        assert parent.markdown[start:end] == chunk.text_content
        assert chunk.source_id == SOURCE_ID
        assert chunk.corpus_version == CORPUS_VERSION


def test_legacy_composition_and_destructive_scripts_are_not_executable() -> None:
    root = Path(__file__).resolve().parents[3]

    assert importlib.util.find_spec("app.infrastructure.ingestion.pipeline") is None
    for relative_path in (
        "scripts/reingest_wiki_lore_only.py",
        "scripts/ingest_production_lore.py",
        "scripts/incremental_ingestion.py",
        "scripts/sync_parents_to_db.py",
        "scripts/clear_ingestion_data.py",
    ):
        assert not (root / relative_path).exists()
