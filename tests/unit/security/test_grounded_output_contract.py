"""Focused RAG-06 tests for the evidence-bound generation contract."""

from __future__ import annotations

import pytest

from app.domain.models.evidence import (
    Evidence,
    EvidenceAccess,
    EvidenceProvenance,
    EvidenceScore,
)
from app.domain.services.guardrails.grounded_output import (
    GroundedOutputAssembler,
    GroundedOutputValidationError,
    build_grounded_response_schema,
)


def _evidence(text: str = "Jinhsi is the Magistrate of Jinzhou.") -> Evidence:
    return Evidence(
        evidence_id="lore:jinhsi",
        kind="lore",
        text=text,
        provenance=EvidenceProvenance(
            source_id="jinhsi", source_type="wiki", collection="character_lore"
        ),
        access=EvidenceAccess(scope="public"),
        score=EvidenceScore(final=0.9),
    )


def _payload(*, text: str, quote: str, evidence_id: str = "lore:jinhsi") -> dict:
    return {
        "decision": "answer",
        "claims": [
            {"text": text, "evidence_id": evidence_id, "evidence_quote": quote}
        ],
        "sentiment": {},
    }


def test_schema_restricts_claims_to_server_selected_evidence_ids() -> None:
    schema = build_grounded_response_schema(
        evidence_ids=["lore:a", "lore:b", "lore:a"],
        sentiment_schema={"type": "object"},
    )

    evidence_property = schema["properties"]["claims"]["items"]["properties"][
        "evidence_id"
    ]
    assert evidence_property["enum"] == ["lore:a", "lore:b"]
    assert schema["additionalProperties"] is False


def test_abstention_is_typed_and_has_no_citations() -> None:
    result = GroundedOutputAssembler().assemble(
        payload={"decision": "abstain", "claims": [], "sentiment": {}},
        evidence=[_evidence()],
        abstention_answer="Not enough evidence.",
    )

    assert result.answer == "Not enough evidence."
    assert result.citations == []
    assert result.abstained is True
    assert result.safety_flags == ["abstained_insufficient_evidence"]


def test_supported_claim_is_delivered_with_server_bound_citation() -> None:
    result = GroundedOutputAssembler().assemble(
        payload=_payload(
            text="Jinhsi is the Magistrate of Jinzhou.",
            quote="Jinhsi is the Magistrate of Jinzhou.",
        ),
        evidence=[_evidence()],
    )

    assert result.answer == "Jinhsi is the Magistrate of Jinzhou."
    assert result.citations == ["lore:jinhsi"]
    assert result.verified_claims == 1
    assert result.extractive_claims == 0


def test_unverified_paraphrase_cannot_reach_sink_and_uses_exact_quote() -> None:
    result = GroundedOutputAssembler().assemble(
        payload=_payload(
            text="Jinhsi secretly rules the Black Shores.",
            quote="Jinhsi is the Magistrate of Jinzhou.",
        ),
        evidence=[_evidence()],
    )

    assert "Black Shores" not in result.answer
    assert result.answer == "Jinhsi is the Magistrate of Jinzhou."
    assert result.safety_flags == ["extractive_quote_fallback"]


def test_quote_not_present_in_selected_evidence_is_rejected() -> None:
    with pytest.raises(GroundedOutputValidationError):
        GroundedOutputAssembler().assemble(
            payload=_payload(
                text="Jinhsi rules the Black Shores.",
                quote="Jinhsi rules the Black Shores.",
            ),
            evidence=[_evidence()],
        )


def test_claim_cannot_bind_to_an_unselected_evidence_identifier() -> None:
    with pytest.raises(GroundedOutputValidationError):
        GroundedOutputAssembler().assemble(
            payload=_payload(
                text="Jinhsi is the Magistrate of Jinzhou.",
                quote="Jinhsi is the Magistrate of Jinzhou.",
                evidence_id="lore:attacker",
            ),
            evidence=[_evidence()],
        )


def test_citation_is_rebound_only_by_exact_quote_in_selected_evidence() -> None:
    distractor = _evidence("The Black Shores studies the Lament.")
    target = _evidence().model_copy(update={"evidence_id": "lore:target"})

    result = GroundedOutputAssembler().assemble(
        payload=_payload(
            text="Jinhsi is the Magistrate of Jinzhou.",
            quote="Jinhsi is the Magistrate of Jinzhou.",
        ),
        evidence=[distractor, target],
    )

    assert result.citations == ["lore:target"]
    assert result.rebound_citations == 1
    assert "citation_rebound" in result.safety_flags


def test_exact_display_quote_resolves_deterministic_mediawiki_link_markup() -> None:
    evidence = _evidence(
        "It blankets [[Solaris-3|Solaris's]] sky and stops space exploration."
    )
    result = GroundedOutputAssembler().assemble(
        payload=_payload(
            text="It blankets Solaris's sky and stops space exploration.",
            quote="It blankets Solaris's sky and stops space exploration.",
        ),
        evidence=[evidence],
    )

    assert result.citations == ["lore:jinhsi"]
    assert result.answer == "It blankets Solaris's sky and stops space exploration."


def test_close_quote_resolves_but_unsupported_claim_uses_canonical_sentence() -> None:
    evidence = _evidence(
        "Jinhsi serves as the Magistrate of Jinzhou and protects its people."
    )
    result = GroundedOutputAssembler().assemble(
        payload=_payload(
            text="Jinhsi secretly rules the Black Shores.",
            quote="Jinhsi serves as Magistrate of Jinzhou and protects its people.",
        ),
        evidence=[evidence],
    )

    assert result.citations == ["lore:jinhsi"]
    assert "serves as the Magistrate" in result.answer
    assert "Black Shores" not in result.answer


def test_distant_quote_is_not_fuzzy_matched_to_unrelated_evidence() -> None:
    with pytest.raises(GroundedOutputValidationError):
        GroundedOutputAssembler().assemble(
            payload=_payload(
                text="Jinhsi rules the Black Shores.",
                quote="Aalto is an information broker from the New Federation.",
            ),
            evidence=[_evidence()],
        )
