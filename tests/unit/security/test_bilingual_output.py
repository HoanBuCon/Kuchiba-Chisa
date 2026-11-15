"""Bilingual evidence-lane output: schema, claim checks and framing limits (GRD-001/003)."""

from __future__ import annotations

import pytest

from app.domain.models.evidence import (
    Evidence,
    EvidenceAccess,
    EvidenceProvenance,
    EvidenceScore,
)
from app.domain.services.guardrails import (
    BilingualOutputAssembler,
    GroundedOutputValidationError,
    build_bilingual_response_schema,
)

QUOTE = "Jinhsi is the Magistrate of Jinzhou and has served for 3 years."
CLAIM_EN = "Jinhsi is the Magistrate of Jinzhou."
CLAIM_VI = "Jinhsi là Magistrate của Jinzhou."
QUESTION = "Jinhsi là ai?"
FALLBACK_LEAD = "Em tra được thế này nè Senpai: "
FRAME = "Em tìm được trong tư liệu gốc nè Senpai: “{quote}”"
ABSTENTION = "Em chưa có đủ bằng chứng nè Senpai."


def _evidence(evidence_id: str = "lore:jinhsi", text: str = QUOTE) -> Evidence:
    return Evidence(
        evidence_id=evidence_id,
        kind="lore",
        text=text,
        provenance=EvidenceProvenance(
            source_id="jinhsi", source_type="wiki", collection="character_lore"
        ),
        access=EvidenceAccess(scope="public"),
        score=EvidenceScore(final=0.9),
    )


def _claim(*, en: str = CLAIM_EN, vi: str = CLAIM_VI, quote: str = QUOTE) -> dict:
    return {"evidence_id": "lore:jinhsi", "quote": quote, "claim_en": en, "claim_vi": vi}


def _payload(*claims: dict, lead: str = "", closing: str = "", decision: str = "answer") -> dict:
    return {
        "decision": decision,
        "lead": lead,
        "claims": list(claims),
        "closing": closing,
        "sentiment": {},
    }


def _assemble(payload: dict, evidence=None):
    return BilingualOutputAssembler().assemble(
        payload=payload,
        evidence=evidence or [_evidence()],
        question=QUESTION,
        abstention_answer=ABSTENTION,
        extractive_frame=FRAME,
        fallback_lead=FALLBACK_LEAD,
    )


def test_schema_has_the_bilingual_shape_and_rejects_unknown_fields() -> None:
    schema = build_bilingual_response_schema(
        evidence_ids=["lore:a", "lore:b", "lore:a"], sentiment_schema={"type": "object"}
    )

    claim = schema["properties"]["claims"]["items"]
    assert set(schema["properties"]) == {"decision", "lead", "claims", "closing", "sentiment"}
    assert set(claim["properties"]) == {"evidence_id", "quote", "claim_en", "claim_vi"}
    assert claim["properties"]["evidence_id"]["enum"] == ["lore:a", "lore:b"]
    assert schema["additionalProperties"] is False
    assert claim["additionalProperties"] is False


def test_schema_requires_selected_evidence() -> None:
    with pytest.raises(ValueError):
        build_bilingual_response_schema(evidence_ids=[], sentiment_schema={})


def test_a_true_bilingual_claim_is_kept_and_shown_in_vietnamese() -> None:
    result = _assemble(_payload(_claim(), lead="Để em kể Senpai nghe nha.", closing="Hết rồi nè."))

    assert result.answer == f"Để em kể Senpai nghe nha. {CLAIM_VI} Hết rồi nè."
    assert result.presented_answer is None
    assert result.citations == ["lore:jinhsi"]
    assert (result.verified_claims, result.removed_claims) == (1, 0)


def test_missing_lead_falls_back_to_the_fixed_lead() -> None:
    result = _assemble(_payload(_claim()))

    assert result.answer == f"{FALLBACK_LEAD.strip()} {CLAIM_VI}"


def test_claim_en_not_supported_by_the_quote_is_dropped() -> None:
    unsupported = _claim(en="Jinhsi commands the Black Shores army.", vi=CLAIM_VI)

    result = _assemble(_payload(unsupported, _claim()))

    assert result.answer.count(CLAIM_VI) == 1
    assert (result.verified_claims, result.removed_claims) == (1, 1)
    assert "unsupported_claim_removed" in result.safety_flags


def test_claim_en_with_a_flipped_negation_is_dropped() -> None:
    flipped = _claim(en="Jinhsi is not the Magistrate of Jinzhou.", vi="Jinhsi không là chức này.")

    result = _assemble(_payload(flipped, _claim()))

    assert (result.verified_claims, result.removed_claims) == (1, 1)


@pytest.mark.parametrize(
    "claim_vi",
    [
        "Ragunna là Magistrate của Jinzhou.",
        "Jinhsi là Magistrate của Jinzhou suốt 9 năm.",
        "Jinhsi không là Magistrate của Jinzhou.",
    ],
)
def test_claim_vi_with_a_swapped_name_extra_number_or_flipped_negation_is_dropped(claim_vi) -> None:
    result = _assemble(_payload(_claim(vi=claim_vi), _claim()))

    assert claim_vi not in result.answer
    assert (result.verified_claims, result.removed_claims) == (1, 1)


def test_a_number_that_is_in_the_quote_is_allowed_in_claim_vi() -> None:
    vi = "Jinhsi đã giữ chức suốt 3 năm."

    result = _assemble(_payload(_claim(en="Jinhsi has served for 3 years.", vi=vi)))

    assert vi in result.answer


def test_lead_with_a_new_name_is_replaced_by_the_fallback() -> None:
    result = _assemble(_payload(_claim(), lead="Ragunna kể rằng Senpai ơi."))

    assert "Ragunna" not in result.answer
    assert result.answer.startswith(FALLBACK_LEAD.strip())


def test_lead_may_reuse_a_name_from_the_question() -> None:
    result = _assemble(_payload(_claim(), lead="Senpai hỏi về Jinhsi nè."))

    assert result.answer.startswith("Senpai hỏi về Jinhsi nè.")


def test_lead_may_name_chisa_herself() -> None:
    result = _assemble(_payload(_claim(), lead="Chisa tra được rồi nè Senpai."))

    assert result.answer.startswith("Chisa tra được rồi nè Senpai.")


def test_lead_that_does_not_address_senpai_is_replaced_by_the_fallback() -> None:
    result = _assemble(_payload(_claim(), lead="Em tra được rồi nè."))

    assert result.answer.startswith(FALLBACK_LEAD.strip())
    assert "Em tra được rồi nè." not in result.answer


def test_closing_with_a_new_number_is_removed() -> None:
    result = _assemble(_payload(_claim(), closing="Em kể được 42 chuyện nữa nha."))

    assert "42" not in result.answer
    assert result.answer.endswith(CLAIM_VI)


def test_all_claims_dropped_falls_back_to_the_extractive_frame() -> None:
    bad = _claim(en="Jinhsi commands the Black Shores army.", vi="Jinhsi chỉ huy quân đội.")

    result = _assemble(_payload(bad, lead="Em biết rồi nè Senpai."))

    assert result.presented_answer == FRAME.format(quote=QUOTE)
    assert result.answer == QUOTE
    assert (result.verified_claims, result.extractive_claims) == (0, 1)
    assert "extractive_quote_fallback" in result.safety_flags
    assert result.citations == ["lore:jinhsi"]


def test_extractive_confidence_counts_each_claim_once() -> None:
    bad = _claim(en="Jinhsi commands the Black Shores army.", vi="Jinhsi chỉ huy quân đội.")
    unresolved = _claim(quote="A line that appears in no evidence item at all.")

    result = _assemble(_payload(bad, unresolved))

    assert (result.extractive_claims, result.removed_claims) == (1, 1)
    assert result.confidence == 0.5


def test_a_quote_missing_from_every_evidence_item_is_rejected() -> None:
    with pytest.raises(GroundedOutputValidationError):
        _assemble(_payload(_claim(quote="A line that appears in no evidence item at all.")))


def test_an_unknown_evidence_id_is_rejected() -> None:
    unknown = _claim() | {"evidence_id": "lore:other"}

    with pytest.raises(GroundedOutputValidationError):
        _assemble(_payload(unknown))


def test_a_quote_that_only_another_item_holds_is_rebound() -> None:
    holder = _evidence("lore:holder", QUOTE)
    cited = _evidence("lore:cited", "Completely different words about weather and tides.")
    claim = _claim() | {"evidence_id": "lore:cited"}

    result = _assemble(_payload(claim), [cited, holder])

    assert result.citations == ["lore:holder"]
    assert result.rebound_citations == 1
    assert "citation_rebound" in result.safety_flags


def test_abstain_decision_returns_the_abstention() -> None:
    result = _assemble(_payload(decision="abstain"))

    assert result.abstained
    assert result.answer == ABSTENTION
    assert result.citations == []


def test_unknown_payload_fields_are_rejected() -> None:
    payload = _payload(_claim()) | {"extra": "x"}

    with pytest.raises(ValueError):
        _assemble(payload)


def test_an_answer_without_claims_is_rejected() -> None:
    with pytest.raises(ValueError):
        _assemble(_payload())


def test_claim_en_with_a_name_absent_from_the_evidence_is_dropped() -> None:
    envelope = _assemble(
        _payload(
            _claim(en="Jinhsi is the Magistrate of Jinzhou and wields Hack.", vi=CLAIM_VI),
            _claim(),
        )
    )

    assert envelope.removed_claims == 1
    assert envelope.verified_claims == 1
