"""Evidence-bound output contract and fail-closed server-side assembly."""

from __future__ import annotations

import html
import re
import unicodedata
from collections.abc import Mapping, Sequence
from difflib import SequenceMatcher
from typing import Any

from app.domain.models.evidence import Evidence
from app.domain.models.grounded_generation import (
    GroundedAnswerEnvelope,
    GroundedModelPayload,
)
from app.domain.services.guardrails.claim_evidence_guard import ClaimEvidenceGuard


class GroundedOutputValidationError(ValueError):
    """Raised when no model claim can be delivered with server evidence."""


def build_grounded_response_schema(
    *,
    evidence_ids: Sequence[str],
    sentiment_schema: Mapping[str, Any],
) -> dict[str, Any]:
    """Build the provider-visible schema from server-selected evidence IDs."""

    allowed_ids = list(dict.fromkeys(item for item in evidence_ids if item))
    if not allowed_ids:
        raise ValueError("grounded output schema requires selected evidence")
    return {
        "type": "object",
        "properties": {
            "decision": {
                "type": "string",
                "enum": ["answer", "abstain"],
                "description": (
                    "Use answer only when selected evidence directly supports the answer; "
                    "otherwise use abstain."
                ),
            },
            "claims": {
                "type": "array",
                "minItems": 0,
                "maxItems": 8,
                "items": {
                    "type": "object",
                    "properties": {
                        "text": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": 2_000,
                            "description": "One concise material answer claim.",
                        },
                        "evidence_id": {
                            "type": "string",
                            "enum": allowed_ids,
                            "description": "The selected evidence item supporting this claim.",
                        },
                        "evidence_quote": {
                            "type": "string",
                            "minLength": 12,
                            "maxLength": 600,
                            "description": (
                                "The shortest exact verbatim span from the selected evidence "
                                "that directly supports the claim."
                            ),
                        },
                    },
                    "required": ["text", "evidence_id", "evidence_quote"],
                    "additionalProperties": False,
                },
            },
            "sentiment": dict(sentiment_schema),
        },
        "required": ["decision", "claims", "sentiment"],
        "additionalProperties": False,
    }


class GroundedOutputAssembler:
    """Remove unsupported prose and bind every delivered segment to evidence."""

    _WHITESPACE = re.compile(r"\s+")
    _WIKI_LINK = re.compile(r"\[\[(?:[^\[\]|]+\|)?([^\[\]]+)\]\]")
    _SENTENCE = re.compile(r"(?<=[.!?])\s+|\n+")
    _MIN_QUOTE_SIMILARITY = 0.82

    def __init__(self, claim_guard: ClaimEvidenceGuard | None = None) -> None:
        self._claim_guard = claim_guard or ClaimEvidenceGuard()

    def assemble(
        self,
        *,
        payload: object,
        evidence: Sequence[Evidence],
        attachment_ids: Sequence[str] = (),
        abstention_answer: str = "Insufficient evidence is available to answer accurately.",
    ) -> GroundedAnswerEnvelope:
        model_payload = GroundedModelPayload.model_validate(payload)
        if model_payload.decision == "abstain":
            return GroundedAnswerEnvelope(
                answer=abstention_answer,
                citations=[],
                confidence=1.0,
                safety_flags=["abstained_insufficient_evidence"],
                attachment_ids=[],
                verified_claims=0,
                extractive_claims=0,
                removed_claims=0,
                rebound_citations=0,
                abstained=True,
            )
        evidence_by_id = {item.evidence_id: item for item in evidence}
        rendered: list[str] = []
        citations: list[str] = []
        verified = 0
        extractive = 0
        removed = 0
        rebound = 0

        for claim in model_payload.claims:
            source = evidence_by_id.get(claim.evidence_id)
            if source is None:
                removed += 1
                continue
            resolved_quote = self._resolve_quote(source.text, claim.evidence_quote)
            if resolved_quote is None:
                rebound_match = next(
                    (
                        (item, quote)
                        for item in evidence
                        if (
                            quote := self._resolve_quote(
                                item.text, claim.evidence_quote
                            )
                        )
                        is not None
                    ),
                    None,
                )
                if rebound_match is None:
                    removed += 1
                    continue
                source, resolved_quote = rebound_match
                rebound += 1

            support_evidence = source.model_copy(update={"text": resolved_quote})
            verification = self._claim_guard.verify(
                answer=claim.text,
                evidence=[support_evidence],
                citation_ids=[source.evidence_id],
            )
            if verification.supported:
                rendered.append(claim.text.strip())
                verified += 1
            else:
                # The model paraphrase is not trusted across languages. The exact,
                # server-verified quote remains a safe extractive answer segment.
                rendered.append(resolved_quote)
                extractive += 1
            if source.evidence_id not in citations:
                citations.append(source.evidence_id)

        if not rendered:
            raise GroundedOutputValidationError(
                "no claim contains an exact quote from its selected evidence"
            )

        flags: list[str] = []
        if extractive:
            flags.append("extractive_quote_fallback")
        if rebound:
            flags.append("citation_rebound")
        if removed:
            flags.append("unsupported_claim_removed")
        accepted = verified + extractive
        confidence = accepted / (accepted + removed)
        return GroundedAnswerEnvelope(
            answer=" ".join(rendered),
            citations=citations,
            confidence=confidence,
            safety_flags=flags,
            attachment_ids=list(dict.fromkeys(attachment_ids)),
            verified_claims=verified,
            extractive_claims=extractive,
            removed_claims=removed,
            rebound_citations=rebound,
            abstained=False,
        )

    @classmethod
    def _contains_quote(cls, evidence_text: str, quote: str) -> bool:
        return cls._resolve_quote(evidence_text, quote) is not None

    @classmethod
    def _resolve_quote(cls, evidence_text: str, quote: str) -> str | None:
        normalized_evidence = cls._normalize(evidence_text)
        normalized_quote = cls._normalize(quote)
        if not normalized_quote:
            return None
        if normalized_quote in normalized_evidence:
            return normalized_quote

        candidates = [
            sentence.strip()
            for sentence in cls._SENTENCE.split(normalized_evidence)
            if sentence.strip()
        ]
        if not candidates:
            return None
        best = max(
            candidates,
            key=lambda sentence: SequenceMatcher(
                None, normalized_quote, sentence
            ).ratio(),
        )
        similarity = SequenceMatcher(None, normalized_quote, best).ratio()
        return best if similarity >= cls._MIN_QUOTE_SIMILARITY else None

    @classmethod
    def _normalize(cls, value: str) -> str:
        display_text = cls._WIKI_LINK.sub(r"\1", html.unescape(value))
        normalized = unicodedata.normalize("NFKC", display_text.replace("''", ""))
        return cls._WHITESPACE.sub(" ", normalized).strip()
