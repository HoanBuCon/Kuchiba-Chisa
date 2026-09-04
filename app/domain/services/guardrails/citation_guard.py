"""Server-side validation of model citation identifiers."""

from __future__ import annotations

from collections.abc import Sequence

from app.domain.models.evidence import Evidence


class CitationValidationError(ValueError):
    """The untrusted model output does not cite the evidence it received."""


class EvidenceCitationGuard:
    """Bind model citation output to evidence IDs selected by the server."""

    def validate(self, citations: object, evidence: Sequence[Evidence]) -> list[str]:
        allowed_ids = {item.evidence_id for item in evidence}
        if not allowed_ids:
            if citations in (None, []):
                return []
            raise CitationValidationError("response contains citations without selected evidence")
        if not isinstance(citations, list) or not citations:
            raise CitationValidationError("evidence-backed response requires citations")
        if not all(isinstance(item, str) and item for item in citations):
            raise CitationValidationError("citation identifiers must be non-empty strings")
        if len(citations) != len(set(citations)):
            raise CitationValidationError("citation identifiers must be unique")
        if not set(citations).issubset(allowed_ids):
            raise CitationValidationError("citation identifier is not in selected evidence")
        return list(citations)
