"""Transport contracts for the curator-only ingestion source registry."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.application.ingestion.source_governance import RegisterIngestionSourceCommand
from app.domain.models.evidence import EvidenceAccess
from app.domain.models.ingestion_source import (
    IngestionSource,
    SourceAccessPolicy,
    SourceStatus,
    SourceTrustTier,
)
from app.domain.models.corpus_release import (
    CorpusQualityReport,
    CorpusRelease,
    CorpusReleaseStatus,
)
from app.domain.models.lore_collections import LoreCollection


class SourceAccessRequest(BaseModel):
    """Requested evidence scope, checked against the verified curator identity."""

    model_config = ConfigDict(extra="forbid")

    scope: Literal["public", "user", "tenant"]
    subject_id: str | None = Field(default=None, min_length=1, max_length=128)
    tenant_id: str | None = Field(default=None, min_length=1, max_length=128)
    channel_id: str | None = Field(default=None, min_length=1, max_length=128)

    def to_domain(self) -> SourceAccessPolicy:
        return SourceAccessPolicy(
            access=EvidenceAccess(
                scope=self.scope,
                subject_id=self.subject_id,
                tenant_id=self.tenant_id,
                channel_id=self.channel_id,
            )
        )


class SourceRegistrationRequest(BaseModel):
    """Content metadata only; source owner and approval actor come from the JWT."""

    model_config = ConfigDict(extra="forbid")

    uri: str = Field(min_length=12, max_length=2_048)
    license_identifier: str = Field(min_length=1, max_length=128)
    access: SourceAccessRequest
    trust_tier: SourceTrustTier
    checksum: str = Field(min_length=64, max_length=64)
    crawl_schedule: str = Field(min_length=9, max_length=256)

    def to_command(self) -> RegisterIngestionSourceCommand:
        return RegisterIngestionSourceCommand(
            uri=self.uri,
            license_identifier=self.license_identifier,
            access_policy=self.access.to_domain(),
            trust_tier=self.trust_tier,
            checksum=self.checksum,
            crawl_schedule=self.crawl_schedule,
        )


class SourceResponse(BaseModel):
    """Curator response without corpus contents or download credentials."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    source_id: uuid.UUID
    uri: str
    owner_id: str
    license_identifier: str
    access: SourceAccessRequest
    trust_tier: SourceTrustTier
    checksum: str
    crawl_schedule: str
    status: SourceStatus
    approved_by: str | None
    approved_at: datetime | None

    @classmethod
    def from_source(cls, source: IngestionSource) -> "SourceResponse":
        access = source.access_policy.access
        return cls(
            source_id=source.source_id,
            uri=source.uri,
            owner_id=source.owner_id,
            license_identifier=source.license_identifier,
            access=SourceAccessRequest(
                scope=access.scope,
                subject_id=access.subject_id,
                tenant_id=access.tenant_id,
                channel_id=access.channel_id,
            ),
            trust_tier=source.trust_tier,
            checksum=source.checksum,
            crawl_schedule=source.crawl_schedule,
            status=source.status,
            approved_by=source.approved_by,
            approved_at=source.approved_at,
        )


class CorpusReleaseResponse(BaseModel):
    """Curator-visible receipt without corpus content or raw evaluator traces."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    release_id: uuid.UUID
    job_id: uuid.UUID
    source_id: uuid.UUID
    logical_collection: LoreCollection
    staging_collection: str
    corpus_version: str
    parent_count: int
    vector_count: int
    parent_manifest_checksum: str
    vector_manifest_checksum: str
    status: CorpusReleaseStatus
    created_at: datetime
    published_at: datetime | None
    previous_active_collection: str | None

    @classmethod
    def from_release(cls, release: CorpusRelease) -> "CorpusReleaseResponse":
        return cls(
            release_id=release.release_id,
            job_id=release.job_id,
            source_id=release.source_id,
            logical_collection=release.logical_collection,
            staging_collection=release.staging_collection,
            corpus_version=release.corpus_version,
            parent_count=release.parent_count,
            vector_count=release.vector_count,
            parent_manifest_checksum=release.parent_manifest_checksum,
            vector_manifest_checksum=release.vector_manifest_checksum,
            status=release.status,
            created_at=release.created_at,
            published_at=release.published_at,
            previous_active_collection=release.previous_active_collection,
        )


class CorpusQualityReportResponse(BaseModel):
    """Aggregate evaluator metrics; raw prompts, answers, and traces are excluded."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    report_id: uuid.UUID
    release_id: uuid.UUID
    evaluator_version: str
    dataset_version: str
    sample_size: int
    confidence_interval: float
    faithfulness: float
    answer_relevance: float
    context_recall: float
    context_precision: float
    citation_correctness: float
    retrieval_hit_at_5: float
    retrieval_mrr_at_10: float
    critical_unsupported_claims: int
    cross_tenant_leakage_count: int
    prompt_leakage_count: int
    human_audit_completed: bool
    security_slice_passed: bool
    evaluated_at: datetime

    @classmethod
    def from_report(cls, report: CorpusQualityReport) -> "CorpusQualityReportResponse":
        return cls.model_validate(report.model_dump())
