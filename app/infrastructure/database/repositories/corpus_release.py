"""SQLAlchemy adapter for durable staged corpus release receipts."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.corpus_release import (
    CorpusQualityReport,
    CorpusRelease,
    CorpusReleaseAuditEvent,
    CorpusReleaseStatus,
)
from app.infrastructure.database.models.ingestion import (
    CorpusReleaseAuditEventModel,
    CorpusReleaseQualityReportModel,
    CorpusReleaseModel,
)


class CorpusReleaseRepository:
    """Persist release metadata only; corpus text remains in its data stores."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save_release(self, release: CorpusRelease) -> None:
        await self._session.merge(self._from_domain(release))
        await self._session.flush()

    async def get_release(self, release_id: uuid.UUID) -> CorpusRelease | None:
        result = await self._session.execute(
            select(CorpusReleaseModel).where(CorpusReleaseModel.id == release_id)
        )
        model = result.scalar_one_or_none()
        return self._to_domain(model) if model is not None else None

    async def get_release_by_staging_collection(
        self, staging_collection: str
    ) -> CorpusRelease | None:
        result = await self._session.execute(
            select(CorpusReleaseModel).where(
                CorpusReleaseModel.staging_collection == staging_collection
            )
        )
        model = result.scalar_one_or_none()
        return self._to_domain(model) if model is not None else None

    async def save_quality_report(self, report: CorpusQualityReport) -> None:
        await self._session.merge(self._quality_from_domain(report))
        await self._session.flush()

    async def get_quality_report(self, release_id: uuid.UUID) -> CorpusQualityReport | None:
        result = await self._session.execute(
            select(CorpusReleaseQualityReportModel).where(
                CorpusReleaseQualityReportModel.release_id == release_id
            )
        )
        model = result.scalar_one_or_none()
        return self._quality_to_domain(model) if model is not None else None

    async def record_audit(self, event: CorpusReleaseAuditEvent) -> None:
        self._session.add(
            CorpusReleaseAuditEventModel(
                id=event.event_id,
                release_id=event.release_id,
                actor_id=event.actor_id,
                action=event.action.value,
                old_status=event.old_status.value if event.old_status is not None else None,
                new_status=event.new_status.value,
                old_corpus_version=event.old_corpus_version,
                new_corpus_version=event.new_corpus_version,
                occurred_at=event.occurred_at,
            )
        )
        await self._session.flush()

    async def commit(self) -> None:
        await self._session.commit()

    @staticmethod
    def _to_domain(model: CorpusReleaseModel) -> CorpusRelease:
        return CorpusRelease(
            release_id=model.id,
            job_id=model.job_id,
            source_id=model.source_id,
            logical_collection=model.logical_collection,
            staging_collection=model.staging_collection,
            corpus_version=model.corpus_version,
            parent_count=model.parent_count,
            vector_count=model.vector_count,
            parent_manifest_checksum=model.parent_manifest_checksum,
            vector_manifest_checksum=model.vector_manifest_checksum,
            status=CorpusReleaseStatus(model.status),
            created_at=model.created_at,
            published_at=model.published_at,
            previous_active_collection=model.previous_active_collection,
        )

    @staticmethod
    def _from_domain(release: CorpusRelease) -> CorpusReleaseModel:
        return CorpusReleaseModel(
            id=release.release_id,
            job_id=release.job_id,
            source_id=release.source_id,
            logical_collection=release.logical_collection.value,
            staging_collection=release.staging_collection,
            corpus_version=release.corpus_version,
            parent_count=release.parent_count,
            vector_count=release.vector_count,
            parent_manifest_checksum=release.parent_manifest_checksum,
            vector_manifest_checksum=release.vector_manifest_checksum,
            status=release.status.value,
            created_at=release.created_at,
            published_at=release.published_at,
            previous_active_collection=release.previous_active_collection,
        )

    @staticmethod
    def _quality_to_domain(model: CorpusReleaseQualityReportModel) -> CorpusQualityReport:
        return CorpusQualityReport(
            report_id=model.id,
            release_id=model.release_id,
            evaluator_version=model.evaluator_version,
            dataset_version=model.dataset_version,
            sample_size=model.sample_size,
            confidence_interval=model.confidence_interval,
            faithfulness=model.faithfulness,
            answer_relevance=model.answer_relevance,
            context_recall=model.context_recall,
            context_precision=model.context_precision,
            citation_correctness=model.citation_correctness,
            retrieval_hit_at_5=model.retrieval_hit_at_5,
            retrieval_mrr_at_10=model.retrieval_mrr_at_10,
            critical_unsupported_claims=model.critical_unsupported_claims,
            cross_tenant_leakage_count=model.cross_tenant_leakage_count,
            prompt_leakage_count=model.prompt_leakage_count,
            human_audit_completed=model.human_audit_completed,
            security_slice_passed=model.security_slice_passed,
            evaluated_at=model.evaluated_at,
        )

    @staticmethod
    def _quality_from_domain(report: CorpusQualityReport) -> CorpusReleaseQualityReportModel:
        return CorpusReleaseQualityReportModel(
            id=report.report_id,
            release_id=report.release_id,
            evaluator_version=report.evaluator_version,
            dataset_version=report.dataset_version,
            sample_size=report.sample_size,
            confidence_interval=report.confidence_interval,
            faithfulness=report.faithfulness,
            answer_relevance=report.answer_relevance,
            context_recall=report.context_recall,
            context_precision=report.context_precision,
            citation_correctness=report.citation_correctness,
            retrieval_hit_at_5=report.retrieval_hit_at_5,
            retrieval_mrr_at_10=report.retrieval_mrr_at_10,
            critical_unsupported_claims=report.critical_unsupported_claims,
            cross_tenant_leakage_count=report.cross_tenant_leakage_count,
            prompt_leakage_count=report.prompt_leakage_count,
            human_audit_completed=report.human_audit_completed,
            security_slice_passed=report.security_slice_passed,
            evaluated_at=report.evaluated_at,
        )
