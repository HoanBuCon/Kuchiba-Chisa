"""Immutable curator approvals for exact corpus-safety false positives."""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class CorpusSafetyProvenance(BaseModel):
    """Canonical identity of one generated corpus chunk."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    source_id: str = Field(min_length=1, max_length=128)
    corpus_version: str = Field(min_length=1, max_length=160)
    page_id: int = Field(ge=0)
    revision_id: int = Field(ge=0)
    chunk_id: str = Field(min_length=36, max_length=36)


class ApprovedCorpusSafetyException(BaseModel):
    """A curator decision bound to one rule and one immutable chunk version."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    exception_id: str = Field(min_length=1, max_length=160)
    status: Literal["approved"]
    rule_id: Literal["sensitive_disclosure"]
    provenance: CorpusSafetyProvenance
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    finding_fingerprint: str = Field(pattern=r"^[0-9a-f]{16}$")
    curator_reason: str = Field(min_length=1, max_length=1000)
    approved_by: str = Field(min_length=1, max_length=128)
    approved_at: datetime
    approval_authority: Literal["user/project owner"]

    @field_validator("approved_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("approved_at must be timezone-aware")
        return value

    def matches(
        self,
        *,
        text: str,
        supplied_checksum: str,
        rule_id: str | None,
        finding_fingerprint: str | None,
        provenance: CorpusSafetyProvenance | None,
    ) -> bool:
        """Require every immutable identity component; no wildcard matching."""

        actual_checksum = hashlib.sha256(text.encode("utf-8")).hexdigest()
        return (
            provenance is not None
            and provenance == self.provenance
            and rule_id == self.rule_id
            and finding_fingerprint == self.finding_fingerprint
            and supplied_checksum == self.content_sha256
            and actual_checksum == self.content_sha256
        )


class CorpusSafetyExceptionManifest(BaseModel):
    """Versioned, auditable set of narrowly scoped curator approvals."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    schema_version: Literal[1]
    purpose: Literal["rag05_staging_evaluation"]
    exceptions: tuple[ApprovedCorpusSafetyException, ...]

    @model_validator(mode="after")
    def require_unique_exception_ids(self) -> CorpusSafetyExceptionManifest:
        ids = [exception.exception_id for exception in self.exceptions]
        if len(ids) != len(set(ids)):
            raise ValueError("corpus safety exception IDs must be unique")
        return self
