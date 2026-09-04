"""FR-ING-005 regressions for reproducible parent and child identities."""

from __future__ import annotations

import uuid

import pytest

from app.application.ingestion.stages.parent_builder_stage import (
    ParentBuilderInput,
    ParentBuilderStage,
)
from app.application.ingestion.stages.metadata_enricher_stage import (
    MetadataEnricherInput,
    MetadataEnricherStage,
)
from app.application.ingestion.stages.semantic_chunk_builder_stage import (
    SemanticChunkBuilderInput,
    SemanticChunkBuilderStage,
)
from app.domain.entities.parser_models import ParsedPage, WikiDocument, WikiSection
from app.domain.models.evidence import EvidenceAccess


class _JobRepository:
    async def log_event(self, *_: object) -> None:
        return None


def _parsed_page(*, revision_id: int = 97, suffix: str = "") -> ParsedPage:
    return ParsedPage(
        page_id=19,
        title="Chisa",
        revision_id=revision_id,
        document=WikiDocument(
            metadata={},
            sections=[
                WikiSection(
                    title="Lore",
                    level=2,
                    content=("Chisa studies at Startorch Academy. " * 30) + suffix,
                )
            ],
            links=[],
            templates=[],
            categories=[],
            infobox={},
            confidence=1.0,
        ),
    )


@pytest.mark.asyncio
async def test_same_versioned_source_build_produces_identical_parent_and_chunk_ids() -> None:
    job_repository = _JobRepository()
    parent_builder = ParentBuilderStage(job_repo=job_repository)
    chunk_builder = SemanticChunkBuilderStage(job_repo=job_repository)
    job_id = uuid.uuid4()

    first_parents = (
        await parent_builder.execute(
            job_id,
            ParentBuilderInput(parsed_page=_parsed_page(), corpus_version="v20260905"),
        )
    ).output
    second_parents = (
        await parent_builder.execute(
            job_id,
            ParentBuilderInput(parsed_page=_parsed_page(), corpus_version="v20260905"),
        )
    ).output
    first_chunks = (
        await chunk_builder.execute(job_id, SemanticChunkBuilderInput(parents=first_parents))
    ).output
    second_chunks = (
        await chunk_builder.execute(job_id, SemanticChunkBuilderInput(parents=second_parents))
    ).output

    assert [parent.id for parent in first_parents] == [parent.id for parent in second_parents]
    assert {parent.corpus_version for parent in first_parents} == {"v20260905"}
    assert [chunk.chunk_id for chunk in first_chunks] == [chunk.chunk_id for chunk in second_chunks]
    assert {chunk.corpus_version for chunk in first_chunks} == {"v20260905"}
    assert [chunk.chunk_hash for chunk in first_chunks] == [chunk.chunk_hash for chunk in second_chunks]

    enriched = (
        await MetadataEnricherStage(job_repo=job_repository).execute(
            job_id,
            MetadataEnricherInput(chunks=first_chunks),
        )
    ).output
    assert {chunk.payload.corpus_version for chunk in enriched if chunk.payload} == {"v20260905"}
    assert {
        chunk.payload.chunk_hash for chunk in enriched if chunk.payload is not None
    } == {chunk.chunk_hash for chunk in first_chunks}


@pytest.mark.asyncio
async def test_changed_source_revision_or_content_produces_new_parent_and_chunk_ids() -> None:
    job_repository = _JobRepository()
    parent_builder = ParentBuilderStage(job_repo=job_repository)
    chunk_builder = SemanticChunkBuilderStage(job_repo=job_repository)
    job_id = uuid.uuid4()

    original = (
        await parent_builder.execute(job_id, ParentBuilderInput(parsed_page=_parsed_page()))
    ).output
    changed = (
        await parent_builder.execute(
            job_id, ParentBuilderInput(parsed_page=_parsed_page(revision_id=98, suffix=" Updated."))
        )
    ).output
    original_chunks = (
        await chunk_builder.execute(job_id, SemanticChunkBuilderInput(parents=original))
    ).output
    changed_chunks = (
        await chunk_builder.execute(job_id, SemanticChunkBuilderInput(parents=changed))
    ).output

    assert original[0].id != changed[0].id
    assert original_chunks[0].chunk_id != changed_chunks[0].chunk_id
    assert original_chunks[0].chunk_hash != changed_chunks[0].chunk_hash


@pytest.mark.asyncio
async def test_source_acl_is_propagated_to_parent_chunk_and_vector_payload() -> None:
    job_repository = _JobRepository()
    access = EvidenceAccess(scope="tenant", tenant_id="guild-a", channel_id="channel-a")
    parents = (
        await ParentBuilderStage(job_repo=job_repository).execute(
            uuid.uuid4(),
            ParentBuilderInput(
                parsed_page=_parsed_page(),
                corpus_version="v20260905",
                source_id=uuid.uuid4(),
                access=access,
            ),
        )
    ).output
    chunks = (
        await SemanticChunkBuilderStage(job_repo=job_repository).execute(
            uuid.uuid4(), SemanticChunkBuilderInput(parents=parents)
        )
    ).output
    enriched = (
        await MetadataEnricherStage(job_repo=job_repository).execute(
            uuid.uuid4(), MetadataEnricherInput(chunks=chunks)
        )
    ).output

    assert {parent.access for parent in parents} == {access}
    assert {chunk.access for chunk in chunks} == {access}
    assert all(chunk.payload is not None for chunk in enriched)
    assert {
        (chunk.payload.access_scope, chunk.payload.access_tenant_id, chunk.payload.access_channel_id)
        for chunk in enriched
        if chunk.payload is not None
    } == {("tenant", "guild-a", "channel-a")}
