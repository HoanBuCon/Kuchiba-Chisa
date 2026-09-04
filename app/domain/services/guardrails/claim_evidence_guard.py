"""Deterministic, fail-closed claim-to-evidence verification for factual output."""

from __future__ import annotations

import math
import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass

from app.domain.models.evidence import Evidence


class ClaimEvidenceValidationError(ValueError):
    """Raised when a factual response contains an unsupported claim."""


@dataclass(frozen=True)
class GroundingVerification:
    verified_claims: int
    unsupported_claims: int
    minimum_claim_score: float

    @property
    def supported(self) -> bool:
        return self.unsupported_claims == 0

    def telemetry(self) -> dict[str, int | float | str]:
        """Metadata-only result: no answer, claim, or evidence text is retained."""
        return {
            "status": "verified" if self.supported else "rejected_unsupported_claim",
            "verified_claims": self.verified_claims,
            "unsupported_claims": self.unsupported_claims,
            "minimum_claim_score": round(self.minimum_claim_score, 3),
        }


class ClaimEvidenceGuard:
    """Verify factual claims against cited, server-selected evidence.

    The guard requires every claim's distinctive terms, and all numeric facts,
    to be present in at least one cited evidence item. It intentionally fails
    closed while a calibrated semantic evaluator is not provisioned.
    """

    _SENTENCE = re.compile(r"(?<=[.!?])\s+|\n+")
    _TOKEN = re.compile(r"[^\W_]+", re.UNICODE)
    _NUMBER = re.compile(r"\d+(?:[.,]\d+)?")
    _STOP_WORDS = frozenset(
        {
            "a", "an", "and", "are", "as", "at", "by", "cho", "có", "của", "cũng",
            "đã", "để", "được", "em", "from", "in", "is", "là", "mà", "mình", "một",
            "những", "of", "on", "or", "rằng", "senpai", "the", "thì", "this", "to", "và",
            "với", "was", "were",
        }
    )
    _ABSTENTION_MARKERS = (
        "chưa có đủ", "không có đủ", "không thể xác", "i don't know",
        "insufficient evidence", "cannot verify",
    )

    def verify(
        self,
        *,
        answer: str,
        evidence: Sequence[Evidence],
        citation_ids: Sequence[str],
    ) -> GroundingVerification:
        cited_ids = set(citation_ids)
        cited_evidence = [item for item in evidence if item.evidence_id in cited_ids]
        if not cited_evidence:
            raise ClaimEvidenceValidationError("factual answer has no cited server evidence")

        verified = 0
        unsupported = 0
        minimum_score = 1.0
        for claim in self._claims(answer):
            if self._is_abstention(claim):
                continue
            score = max(self._claim_score(claim, item.text) for item in cited_evidence)
            minimum_score = min(minimum_score, score)
            if score < self._required_score(claim):
                unsupported += 1
            else:
                verified += 1

        if verified == 0 and unsupported == 0:
            unsupported = 1
            minimum_score = 0.0
        return GroundingVerification(verified, unsupported, minimum_score)

    def require_supported(
        self,
        *,
        answer: str,
        evidence: Sequence[Evidence],
        citation_ids: Sequence[str],
    ) -> GroundingVerification:
        result = self.verify(answer=answer, evidence=evidence, citation_ids=citation_ids)
        if not result.supported:
            raise ClaimEvidenceValidationError("response contains unsupported factual claims")
        return result

    @classmethod
    def _claims(cls, answer: str) -> list[str]:
        return [segment.strip() for segment in cls._SENTENCE.split(answer) if segment.strip()]

    @classmethod
    def _claim_score(cls, claim: str, evidence_text: str) -> float:
        claim_terms = cls._terms(claim)
        if not claim_terms:
            return 0.0
        evidence_terms = cls._terms(evidence_text)
        overlap = len(claim_terms & evidence_terms) / len(claim_terms)
        claim_numbers = set(cls._NUMBER.findall(cls._normalize(claim)))
        evidence_numbers = set(cls._NUMBER.findall(cls._normalize(evidence_text)))
        if claim_numbers and not claim_numbers.issubset(evidence_numbers):
            return 0.0
        return overlap

    @classmethod
    def _required_score(cls, claim: str) -> float:
        count = len(cls._terms(claim))
        return 1.0 if count <= 2 else math.ceil(count * 0.5) / count

    @classmethod
    def _terms(cls, text: str) -> set[str]:
        return {
            token
            for token in cls._TOKEN.findall(cls._normalize(text))
            if token not in cls._STOP_WORDS and (len(token) >= 3 or token.isdigit())
        }

    @staticmethod
    def _normalize(text: str) -> str:
        return unicodedata.normalize("NFKC", text).casefold()

    @classmethod
    def _is_abstention(cls, claim: str) -> bool:
        normalized = cls._normalize(claim)
        return any(marker in normalized for marker in cls._ABSTENTION_MARKERS)
