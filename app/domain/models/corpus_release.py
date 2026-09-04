"""Durable, non-content metadata for a staged corpus release."""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain.models.lore_collections import (
    LoreCollection,
    corpus_version_from_staging_collection,
    logical_collection_from_staging_collection,
    validate_lore_staging_collection,
)

_SHA256 = re.compile(r"[0-9a-f]{64}")


class CorpusReleaseStatus(StrEnum):
    """Only a quality-approved staged release can be published."""

    STAGED = "staged"
    QUALITY_PASSED = "quality_passed"
    PROMOTION_REQUESTED = "promotion_requested"
    PUBLISHED = "published"
    ROLLBACK_REQUESTED = "rollback_requested"
    ROLLED_BACK = "rolled_back"
    FAILED = "failed"


class CorpusReleaseAuditAction(StrEnum):
    STAGED = "staged"
    QUALITY_PASSED = "quality_passed"
    PROMOTION_REQUESTED = "promotion_requested"
    PUBLISHED = "published"
    ROLLBACK_REQUESTED = "rollback_requested"
    ROLLED_BACK = "rolled_back"
    FAILED = "failed"


class CorpusQualityReport(BaseModel):
    """Trusted evaluator output required before a staged release can be promoted."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    report_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    release_id: uuid.UUID
    evaluator_version: str = Field(min_length=1, max_length=128)
    dataset_version: str = Field(min_length=1, max_length=128)
    sample_size: int = Field(ge=1)
    confidence_interval: float = Field(ge=0.0, le=1.0)
    faithfulness: float = Field(ge=0.0, le=1.0)
    answer_relevance: float = Field(ge=0.0, le=1.0)
    context_recall: float = Field(ge=0.0, le=1.0)
    context_precision: float = Field(ge=0.0, le=1.0)
    citation_correctness: float = Field(ge=0.0, le=1.0)
    retrieval_hit_at_5: float = Field(ge=0.0, le=1.0)
    retrieval_mrr_at_10: float = Field(ge=0.0, le=1.0)
    critical_unsupported_claims: int = Field(ge=0)
    cross_tenant_leakage_count: int = Field(ge=0)
    prompt_leakage_count: int = Field(ge=0)
    human_audit_completed: bool
    security_slice_passed: bool
    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("evaluated_at")
    @classmethod
    def normalize_evaluated_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("quality report timestamp must include a timezone")
        return value.astimezone(UTC)

    @property
    def passes_release_gate(self) -> bool:
        """SRS NFR-RAG thresholds plus mandatory zero-leakage security slices."""
        return (
            self.faithfulness >= 0.90
            and self.answer_relevance >= 0.85
            and self.context_recall >= 0.85
            and self.context_precision >= 0.75
            and self.citation_correctness >= 0.95
            and self.retrieval_hit_at_5 >= 0.90
            and self.retrieval_mrr_at_10 >= 0.80
            and self.critical_unsupported_claims == 0
            and self.cross_tenant_leakage_count == 0
            and self.prompt_leakage_count == 0
            and self.human_audit_completed
            and self.security_slice_passed
        )


class CorpusRelease(BaseModel):
    """Verified staging receipt; no corpus text or unredacted evaluation input."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    release_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    job_id: uuid.UUID
    source_id: uuid.UUID
    logical_collection: LoreCollection
    staging_collection: str = Field(min_length=4, max_length=192)
    corpus_version: str = Field(min_length=1, max_length=64)
    parent_count: int = Field(ge=0)
    vector_count: int = Field(ge=0)
    parent_manifest_checksum: str = Field(min_length=64, max_length=64)
    vector_manifest_checksum: str = Field(min_length=64, max_length=64)
    status: CorpusReleaseStatus = CorpusReleaseStatus.STAGED
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    published_at: datetime | None = None
    previous_active_collection: str | None = Field(default=None, max_length=192)

    @field_validator("staging_collection")
    @classmethod
    def require_versioned_staging_collection(cls, value: str) -> str:
        return validate_lore_staging_collection(value)

    @field_validator("parent_manifest_checksum", "vector_manifest_checksum")
    @classmethod
    def require_checksum(cls, value: str) -> str:
        checksum = value.lower()
        if _SHA256.fullmatch(checksum) is None:
            raise ValueError("corpus release manifest must be a SHA-256 hexadecimal digest")
        return checksum

    @field_validator("created_at", "published_at")
    @classmethod
    def normalize_datetime(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("corpus release timestamps must include a timezone")
        return value.astimezone(UTC) if value is not None else None

    @model_validator(mode="after")
    def require_consistent_staging_identity(self) -> "CorpusRelease":
        if logical_collection_from_staging_collection(self.staging_collection) != self.logical_collection:
            raise ValueError("release logical collection does not match its staging target")
        if corpus_version_from_staging_collection(self.staging_collection) != self.corpus_version:
            raise ValueError("release corpus version does not match its staging target")
        active_statuses = {
            CorpusReleaseStatus.PUBLISHED,
            CorpusReleaseStatus.ROLLBACK_REQUESTED,
        }
        if self.status in active_statuses and self.published_at is None:
            raise ValueError("active release state requires a publication timestamp")
        if self.status not in active_statuses and self.published_at is not None:
            raise ValueError("only an active release state can carry a publication timestamp")
        return self

    def mark_quality_passed(self, report: CorpusQualityReport) -> "CorpusRelease":
        """Permit publication only after the evaluated receipt clears every SRS threshold."""
        if self.status is not CorpusReleaseStatus.STAGED:
            raise ValueError("only staged releases can receive a quality decision")
        if report.release_id != self.release_id:
            raise ValueError("quality report belongs to another corpus release")
        if not report.passes_release_gate:
            raise ValueError("quality report does not meet the corpus release gate")
        return self.model_copy(update={"status": CorpusReleaseStatus.QUALITY_PASSED})

    def mark_published(
        self,
        *,
        previous_active_collection: str | None,
        published_at: datetime | None = None,
    ) -> "CorpusRelease":
        """Represent a successful external alias swap, never a planned publication."""
        if self.status is not CorpusReleaseStatus.PROMOTION_REQUESTED:
            raise ValueError("only a committed promotion request can be published")
        return self.model_copy(
            update={
                "status": CorpusReleaseStatus.PUBLISHED,
                "published_at": published_at or datetime.now(UTC),
                "previous_active_collection": previous_active_collection,
            }
        )

    def mark_promotion_requested(
        self, *, previous_active_collection: str
    ) -> "CorpusRelease":
        """Durably record the recoverable intent before mutating Qdrant aliases."""
        if self.status is not CorpusReleaseStatus.QUALITY_PASSED:
            raise ValueError("only a quality-passed release can request promotion")
        if not previous_active_collection:
            raise ValueError("promotion requires a retained active rollback target")
        return self.model_copy(
            update={
                "status": CorpusReleaseStatus.PROMOTION_REQUESTED,
                "previous_active_collection": previous_active_collection,
            }
        )

    def restore_quality_passed(self) -> "CorpusRelease":
        """Return an unexecuted promotion intent to its safe, publishable state."""
        if self.status is not CorpusReleaseStatus.PROMOTION_REQUESTED:
            raise ValueError("only a promotion request can return to quality-passed")
        return self.model_copy(
            update={
                "status": CorpusReleaseStatus.QUALITY_PASSED,
                "previous_active_collection": None,
            }
        )

    def mark_rolled_back(self) -> "CorpusRelease":
        """Retain receipt history after a successful atomic rollback."""
        if self.status is not CorpusReleaseStatus.ROLLBACK_REQUESTED:
            raise ValueError("only a committed rollback request can be completed")
        return self.model_copy(
            update={"status": CorpusReleaseStatus.ROLLED_BACK, "published_at": None}
        )

    def mark_rollback_requested(self) -> "CorpusRelease":
        """Durably record a reversible rollback intent before changing the active alias."""
        if self.status is not CorpusReleaseStatus.PUBLISHED:
            raise ValueError("only a published release can request rollback")
        if self.previous_active_collection is None:
            raise ValueError("rollback requires a retained prior collection")
        return self.model_copy(update={"status": CorpusReleaseStatus.ROLLBACK_REQUESTED})

    def restore_published(self) -> "CorpusRelease":
        """Restore the active state when a durable rollback intent did not alter the alias."""
        if self.status is not CorpusReleaseStatus.ROLLBACK_REQUESTED:
            raise ValueError("only a rollback request can return to published")
        return self.model_copy(update={"status": CorpusReleaseStatus.PUBLISHED})


class CorpusReleaseAuditEvent(BaseModel):
    """Append-only actor/version audit record for corpus lifecycle actions."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    release_id: uuid.UUID
    actor_id: str = Field(min_length=1, max_length=128)
    action: CorpusReleaseAuditAction
    old_status: CorpusReleaseStatus | None = None
    new_status: CorpusReleaseStatus
    old_corpus_version: str | None = Field(default=None, min_length=1, max_length=64)
    new_corpus_version: str = Field(min_length=1, max_length=64)
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("occurred_at")
    @classmethod
    def normalize_occurrence(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("corpus release audit timestamp must include a timezone")
        return value.astimezone(UTC)
