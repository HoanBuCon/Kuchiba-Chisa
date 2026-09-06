"""Typed contracts for evidence-bound factual generation."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class GroundedClaimCandidate(BaseModel):
    """Untrusted claim proposed by the model and bound to one evidence item."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    text: str = Field(min_length=1, max_length=2_000)
    evidence_id: str = Field(min_length=1, max_length=512)
    evidence_quote: str = Field(min_length=12, max_length=600)


class GroundedModelPayload(BaseModel):
    """Provider payload validated before claim/evidence assembly."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    decision: Literal["answer", "abstain"]
    claims: list[GroundedClaimCandidate] = Field(max_length=8)
    sentiment: dict[str, Any]

    @model_validator(mode="after")
    def validate_decision_claims(self) -> GroundedModelPayload:
        if self.decision == "answer" and not self.claims:
            raise ValueError("answer decision requires at least one claim")
        if self.decision == "abstain" and self.claims:
            raise ValueError("abstain decision cannot contain claims")
        return self


class GroundedAnswerEnvelope(BaseModel):
    """Server-owned terminal generation result for downstream delivery."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    answer: str = Field(min_length=1)
    citations: list[str]
    confidence: float = Field(ge=0.0, le=1.0)
    safety_flags: list[
        Literal[
            "abstained_insufficient_evidence",
            "citation_rebound",
            "extractive_quote_fallback",
            "unsupported_claim_removed",
        ]
    ] = Field(default_factory=list)
    attachment_ids: list[str] = Field(default_factory=list)
    verified_claims: int = Field(ge=0)
    extractive_claims: int = Field(ge=0)
    removed_claims: int = Field(ge=0)
    rebound_citations: int = Field(ge=0)
    abstained: bool = False
