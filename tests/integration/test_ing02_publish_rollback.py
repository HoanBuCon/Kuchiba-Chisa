"""ING-02 isolated PostgreSQL/Qdrant publish-and-rollback verification."""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime

import pytest
from qdrant_client import AsyncQdrantClient
from qdrant_client.http.models import PointStruct, SparseVector
from sqlalchemy import select

from app.application.ingestion.corpus_release_lifecycle import CorpusReleaseLifecycleService
from app.config.settings import settings
from app.domain.entities.lore import LoreParent
from app.domain.models.corpus_release import (
    CorpusQualityReport,
    CorpusRelease,
    CorpusReleaseStatus,
)
from app.domain.models.evidence import EvidenceAccess
from app.domain.models.ingestion_source import (
    IngestionSource,
    SourceAccessPolicy,
    SourceStatus,
    SourceTrustTier,
)
from app.domain.value_objects.principal import PrincipalContext
from app.infrastructure.database.engine import AsyncSessionFactory
from app.infrastructure.database.models.ingestion import (
    CorpusReleaseAuditEventModel,
    PipelineJobModel,
)
from app.infrastructure.database.repositories.corpus_release import CorpusReleaseRepository
from app.infrastructure.database.repositories.ingestion_source import IngestionSourceRepository
from app.infrastructure.database.repositories.lore_parent import LoreParentRepository
from app.infrastructure.vector.qdrant.qdrant_service import QdrantService


def _source(source_id: uuid.UUID) -> IngestionSource:
    return IngestionSource(
        source_id=source_id,
        uri="https://example.invalid/ing02-isolated",
        owner_id="ing02-curator",
        license_identifier="isolated-test",
        access_policy=SourceAccessPolicy(access=EvidenceAccess(scope="public")),
        trust_tier=SourceTrustTier.REVIEWED,
        checksum="a" * 64,
        crawl_schedule="0 3 * * *",
        status=SourceStatus.APPROVED,
        approved_by="ing02-curator",
        approved_at=datetime.now(UTC),
    )


def _parent(source_id: uuid.UUID, version: str, marker: str) -> LoreParent:
    return LoreParent(
        id=uuid.uuid4(),
        page_id=1 if marker == "prior" else 2,
        page_title=f"ING-02 {marker}",
        heading="Lead",
        markdown=f"Isolated {marker} corpus content.",
        source_file=f"{marker}.wikitext",
        revision_id=1,
        corpus_version=version,
        source_id=source_id,
        access=EvidenceAccess(scope="public"),
    )


def _payload(parent: LoreParent, point_id: uuid.UUID) -> dict[str, object]:
    return {
        "chunk_hash": hashlib.sha256(f"chunk:{point_id}".encode()).hexdigest(),
        "parent_id": str(parent.id),
        "source_id": str(parent.source_id),
        "corpus_version": parent.corpus_version,
        "access_scope": "public",
        "access_subject_id": None,
        "access_tenant_id": None,
        "access_channel_id": None,
    }


async def _stage_vector(
    service: QdrantService,
    client: AsyncQdrantClient,
    parent: LoreParent,
) -> tuple[str, str]:
    assert parent.corpus_version is not None
    collection = await service.prepare_versioned_collection(
        "character_lore",
        parent.corpus_version,
        settings.QDRANT_EMBEDDING_DIM,
    )
    point_id = uuid.uuid4()
    await client.upsert(
        collection_name=collection,
        wait=True,
        points=[
            PointStruct(
                id=str(point_id),
                vector={
                    "dense": [0.01] * settings.QDRANT_EMBEDDING_DIM,
                    "bm25": SparseVector(indices=[1], values=[1.0]),
                },
                payload=_payload(parent, point_id),
            )
        ],
    )
    checksum = await service.staged_lore_manifest_checksum(
        collection=collection,
        corpus_version=parent.corpus_version,
        expected_point_count=1,
    )
    return collection, checksum


def _quality(release_id: uuid.UUID) -> CorpusQualityReport:
    return CorpusQualityReport(
        release_id=release_id,
        evaluator_version="ing02-isolated-v1",
        dataset_version="ing02-isolated-v1",
        sample_size=1,
        confidence_interval=0.0,
        faithfulness=1.0,
        answer_relevance=1.0,
        context_recall=1.0,
        context_precision=1.0,
        citation_correctness=1.0,
        retrieval_hit_at_5=1.0,
        retrieval_mrr_at_10=1.0,
        critical_unsupported_claims=0,
        cross_tenant_leakage_count=0,
        prompt_leakage_count=0,
        human_audit_completed=True,
        security_slice_passed=True,
    )


@pytest.mark.asyncio
async def test_isolated_publish_and_rollback_are_atomic_and_durably_audited() -> None:
    assert settings.is_test
    assert settings.QDRANT_URL.rstrip("/") in {
        "http://localhost:16333",
        "http://qdrant:6333",
    }
    run_suffix = uuid.uuid4().hex[:10]
    prior_version = f"ing02prior_{run_suffix}"
    candidate_version = f"ing02candidate_{run_suffix}"
    source_id = uuid.uuid4()
    client = AsyncQdrantClient(url=settings.QDRANT_URL, timeout=30)
    publisher = QdrantService(client=client)

    async with AsyncSessionFactory() as session:
        source_repository = IngestionSourceRepository(session)
        parent_repository = LoreParentRepository(session)
        release_repository = CorpusReleaseRepository(session)
        prior_parent = _parent(source_id, prior_version, "prior")
        candidate_parent = _parent(source_id, candidate_version, "candidate")

        await source_repository.save_source(_source(source_id))
        await parent_repository.save_parent(prior_parent)
        await parent_repository.save_parent(candidate_parent)

        prior_job_id = uuid.uuid4()
        candidate_job_id = uuid.uuid4()
        session.add_all(
            [
                PipelineJobModel(id=prior_job_id, stage="ing02", status="SUCCEEDED"),
                PipelineJobModel(id=candidate_job_id, stage="ing02", status="SUCCEEDED"),
            ]
        )
        await session.flush()

        prior_collection, prior_vector_checksum = await _stage_vector(
            publisher, client, prior_parent
        )
        candidate_collection, candidate_vector_checksum = await _stage_vector(
            publisher, client, candidate_parent
        )
        prior_parent_manifest = await parent_repository.get_corpus_manifest(
            source_id=source_id, corpus_version=prior_version
        )
        candidate_parent_manifest = await parent_repository.get_corpus_manifest(
            source_id=source_id, corpus_version=candidate_version
        )

        prior_release = CorpusRelease(
            job_id=prior_job_id,
            source_id=source_id,
            logical_collection="character_lore",
            staging_collection=prior_collection,
            corpus_version=prior_version,
            parent_count=1,
            vector_count=1,
            parent_manifest_checksum=prior_parent_manifest.checksum,
            vector_manifest_checksum=prior_vector_checksum,
            status=CorpusReleaseStatus.PUBLISHED,
            published_at=datetime.now(UTC),
        )
        candidate_release = CorpusRelease(
            job_id=candidate_job_id,
            source_id=source_id,
            logical_collection="character_lore",
            staging_collection=candidate_collection,
            corpus_version=candidate_version,
            parent_count=1,
            vector_count=1,
            parent_manifest_checksum=candidate_parent_manifest.checksum,
            vector_manifest_checksum=candidate_vector_checksum,
        )
        await release_repository.save_release(prior_release)
        await release_repository.save_release(candidate_release)
        await release_repository.commit()

        await publisher.promote_active_alias(
            "character_lore",
            prior_collection,
            expected_point_count=1,
            expected_corpus_version=prior_version,
            expected_manifest_checksum=prior_vector_checksum,
        )
        service = CorpusReleaseLifecycleService(
            release_repository=release_repository,
            source_repository=source_repository,
            parent_repository=parent_repository,
            publisher=publisher,
        )
        quality_passed = await service.record_quality_report(_quality(candidate_release.release_id))
        principal = PrincipalContext(
            subject_id="ing02-curator",
            tenant_id=None,
            channel_id=None,
            source="web",
            kind="user",
            scopes=frozenset(
                {
                    "ingestion:release:publish",
                    "ingestion:release:rollback",
                }
            ),
        )

        assert quality_passed.status is CorpusReleaseStatus.QUALITY_PASSED
        published = await service.publish(principal, candidate_release.release_id)
        assert published.status is CorpusReleaseStatus.PUBLISHED
        assert await publisher.active_target("character_lore") == candidate_collection

        rolled_back = await service.rollback(principal, candidate_release.release_id)
        assert rolled_back.status is CorpusReleaseStatus.ROLLED_BACK
        assert await publisher.active_target("character_lore") == prior_collection

        actions = (
            await session.execute(
                select(CorpusReleaseAuditEventModel.action)
                .where(CorpusReleaseAuditEventModel.release_id == candidate_release.release_id)
                .order_by(CorpusReleaseAuditEventModel.occurred_at)
            )
        ).scalars().all()
        assert actions == [
            "quality_passed",
            "promotion_requested",
            "published",
            "rollback_requested",
            "rolled_back",
        ]
        assert await client.collection_exists(prior_collection)
        assert await client.collection_exists(candidate_collection)

    await client.close()
