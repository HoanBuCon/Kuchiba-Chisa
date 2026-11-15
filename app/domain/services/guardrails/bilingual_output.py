"""Evidence-lane output: bilingual claims checked literally, shown in Vietnamese (GRD-001)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from app.domain.models.evidence import Evidence
from app.domain.models.grounded_generation import (
    MAX_CLAIM_CHARS,
    MAX_CLAIMS,
    MAX_FRAMING_CHARS,
    MAX_QUOTE_CHARS,
    MIN_QUOTE_CHARS,
    BilingualClaimCandidate,
    BilingualModelPayload,
    GroundedAnswerEnvelope,
)
from app.domain.services.guardrails.claim_evidence_guard import ClaimEvidenceGuard
from app.domain.services.guardrails.field_claims import states_field
from app.domain.services.guardrails.grounded_output import (
    GroundedOutputAssembler,
    GroundedOutputValidationError,
)
from app.domain.services.guardrails.literal_facts import (
    facts_match,
    introduces_new_facts,
    invents_names,
    negation_agrees,
)

ADDRESSEE = "Senpai"
SELF_NAME = "Chisa"

SafetyFlag = Literal[
    "citation_rebound", "extractive_quote_fallback", "unsupported_claim_removed"
]


def build_bilingual_response_schema(
    *,
    evidence_ids: Sequence[str],
    sentiment_schema: Mapping[str, Any],
) -> dict[str, Any]:
    """Provider-visible schema: server-chosen evidence IDs, unknown fields rejected."""

    allowed_ids = list(dict.fromkeys(item for item in evidence_ids if item))
    if not allowed_ids:
        raise ValueError("grounded output schema requires selected evidence")
    claim = {
        "type": "object",
        "properties": {
            "evidence_id": {
                "type": "string",
                "enum": allowed_ids,
                "description": "The selected evidence item supporting this claim.",
            },
            "quote": {
                "type": "string",
                "minLength": MIN_QUOTE_CHARS,
                "maxLength": MAX_QUOTE_CHARS,
                "description": "The shortest exact verbatim span of the evidence behind the claim.",
            },
            "claim_en": {
                "type": "string",
                "minLength": 1,
                "maxLength": MAX_CLAIM_CHARS,
                "description": "The claim in English, stating only what the quote states.",
            },
            "claim_vi": {
                "type": "string",
                "minLength": 1,
                "maxLength": MAX_CLAIM_CHARS,
                "description": "The same claim in natural Vietnamese, names and numbers unchanged.",
            },
        },
        "required": ["evidence_id", "quote", "claim_en", "claim_vi"],
        "additionalProperties": False,
    }
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
            "lead": {
                "type": "string",
                "maxLength": MAX_FRAMING_CHARS,
                "description": "One short in-voice Vietnamese sentence, no new names or numbers.",
            },
            "claims": {
                "type": "array",
                "minItems": 0,
                "maxItems": MAX_CLAIMS,
                "items": claim,
            },
            "closing": {
                "type": "string",
                "maxLength": MAX_FRAMING_CHARS,
                "description": "Optional short in-voice Vietnamese sentence, or empty.",
            },
            "sentiment": dict(sentiment_schema),
        },
        "required": ["decision", "lead", "claims", "closing", "sentiment"],
        "additionalProperties": False,
    }


@dataclass(frozen=True)
class _BoundClaim:
    claim: BilingualClaimCandidate
    source: Evidence
    quote: str
    rebound: bool


class BilingualOutputAssembler:
    """Drops every claim that fails a literal check; framing may not add names or numbers."""

    def __init__(self, claim_guard: ClaimEvidenceGuard | None = None) -> None:
        self._claim_guard = claim_guard or ClaimEvidenceGuard()

    def assemble(
        self,
        *,
        payload: object,
        evidence: Sequence[Evidence],
        question: str,
        abstention_answer: str,
        extractive_frame: str,
        fallback_lead: str,
    ) -> GroundedAnswerEnvelope:
        """The frame and fallback lead are the server's voice when the model's cannot be used."""
        model = BilingualModelPayload.model_validate(payload)
        if model.decision == "abstain":
            return _abstention(abstention_answer)
        bound = [item for claim in model.claims if (item := self._bind(claim, evidence))]
        if not bound:
            raise GroundedOutputValidationError(
                "no claim contains an exact quote from its selected evidence"
            )
        kept = [item for item in bound if self._is_supported(item)]
        removed = len(model.claims) - len(kept)
        if not kept:
            return self._extractive(bound, len(model.claims), extractive_frame)
        return self._answer(model, kept, removed, question, fallback_lead)

    def _bind(
        self, claim: BilingualClaimCandidate, evidence: Sequence[Evidence]
    ) -> _BoundClaim | None:
        cited = next((item for item in evidence if item.evidence_id == claim.evidence_id), None)
        if cited is None:
            return None
        for item in (cited, *(other for other in evidence if other is not cited)):
            quote = GroundedOutputAssembler.resolve_quote(item.text, claim.quote)
            if quote is not None:
                return _BoundClaim(claim, item, quote, rebound=item is not cited)
        return None

    def _is_supported(self, bound: _BoundClaim) -> bool:
        claim = bound.claim
        support = bound.source.model_copy(update={"text": bound.quote})
        english = self._claim_guard.verify(
            answer=claim.claim_en,
            evidence=[support],
            citation_ids=[bound.source.evidence_id],
        )
        return (
            (english.supported or states_field(claim.claim_en, bound.quote))
            and not invents_names(claim.claim_en, f"{bound.source.text} {bound.quote}")
            and negation_agrees(claim.claim_en, bound.quote)
            and facts_match(claim.claim_vi, claim.claim_en, bound.source.text)
        )

    def _answer(
        self,
        model: BilingualModelPayload,
        kept: Sequence[_BoundClaim],
        removed: int,
        question: str,
        fallback_lead: str,
    ) -> GroundedAnswerEnvelope:
        sentences = [_one_line(item.claim.claim_vi) for item in kept]
        # Chisa naming herself and addressing Senpai is voice, not a new fact.
        known = " ".join(
            [SELF_NAME, ADDRESSEE, question, *sentences, *(item.claim.claim_en for item in kept)]
        )
        lead = _vetted(model.lead, known)
        if ADDRESSEE not in lead:
            lead = fallback_lead.strip()
        text = " ".join(part for part in (lead, *sentences, _vetted(model.closing, known)) if part)
        rebound = sum(item.rebound for item in kept)
        return GroundedAnswerEnvelope(
            answer=text,
            citations=_citations(kept),
            confidence=len(kept) / (len(kept) + removed),
            safety_flags=_flags(removed=removed, rebound=rebound),
            verified_claims=len(kept),
            extractive_claims=0,
            removed_claims=removed,
            rebound_citations=rebound,
        )

    def _extractive(
        self, bound: Sequence[_BoundClaim], total: int, frame: str
    ) -> GroundedAnswerEnvelope:
        quotes = list(dict.fromkeys(item.quote for item in bound))
        rebound = sum(item.rebound for item in bound)
        return GroundedAnswerEnvelope(
            answer=" ".join(quotes),
            presented_answer=frame.format(quote=" ".join(quotes)),
            citations=_citations(bound),
            confidence=len(bound) / total,
            safety_flags=_flags(removed=total - len(bound), rebound=rebound, extractive=True),
            verified_claims=0,
            extractive_claims=len(quotes),
            removed_claims=total - len(bound),
            rebound_citations=rebound,
        )


def _abstention(answer: str) -> GroundedAnswerEnvelope:
    return GroundedAnswerEnvelope(
        answer=answer,
        citations=[],
        confidence=1.0,
        safety_flags=["abstained_insufficient_evidence"],
        verified_claims=0,
        extractive_claims=0,
        removed_claims=0,
        rebound_citations=0,
        abstained=True,
    )


def _one_line(text: str) -> str:
    return " ".join(text.split())


def _vetted(text: str, known: str) -> str:
    """Framing that names or counts something the claims and question do not is dropped."""
    line = _one_line(text)
    return "" if introduces_new_facts(line, known) else line


def _citations(items: Sequence[_BoundClaim]) -> list[str]:
    return list(dict.fromkeys(item.source.evidence_id for item in items))


def _flags(*, removed: int, rebound: int, extractive: bool = False) -> list[SafetyFlag]:
    flags: list[SafetyFlag] = []
    if extractive:
        flags.append("extractive_quote_fallback")
    if rebound:
        flags.append("citation_rebound")
    if removed:
        flags.append("unsupported_claim_removed")
    return flags
