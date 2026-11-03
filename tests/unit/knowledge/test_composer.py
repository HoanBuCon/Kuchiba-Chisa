"""Grounded Composer: bound claims, abstaining, leakage and citation snapshots (GRD-001..005)."""

from uuid import uuid4

from app.domain.entities.emotion import EmotionState
from app.domain.interfaces.llm_provider import LLMCallBudget, LLMPurpose, LLMResponse
from app.domain.models.evidence import (
    Evidence,
    EvidenceAccess,
    EvidenceProvenance,
    EvidenceScore,
)
from app.domain.services.chisa_voice import (
    GROUNDED_ABSTENTION,
    GROUNDED_ANSWER_LEAD,
    GROUNDED_LIST_LEAD,
)
from app.domain.services.context_builder import ContextBuilder
from app.domain.services.knowledge.composer import GroundedComposer

TEXT = "Chisa studies at Startorch Academy in the Lahai-Roi region."
SENTIMENT = {"joy_delta": 0.0}


def _evidence(text=TEXT, evidence_id="wiki:1:a") -> Evidence:
    return Evidence(
        evidence_id=evidence_id,
        kind="lore",
        text=text,
        provenance=EvidenceProvenance(
            source_id="https://w/Chisa",
            source_type="canon",
            collection="lore_canon",
            source_version="v1",
            source_revision=7,
            page_id=1,
        ),
        access=EvidenceAccess(scope="public"),
        score=EvidenceScore(final=1.0),
    )


class FakeLLM:
    def __init__(self, parsed) -> None:
        self.parsed = parsed
        self.prompts = []

    async def generate(self, prompt):
        self.prompts.append(prompt)
        return LLMResponse(raw_content="{}", parsed=self.parsed)


def _claim(text=TEXT, quote=TEXT, evidence_id="wiki:1:a") -> dict:
    return {"text": text, "evidence_id": evidence_id, "evidence_quote": quote}


def _answer(*claims) -> dict:
    return {"decision": "answer", "claims": list(claims), "sentiment": SENTIMENT}


async def _compose(llm, evidence=None):
    return await GroundedComposer(llm, ContextBuilder()).compose(
        "Chisa học ở đâu?",
        [_evidence()] if evidence is None else evidence,
        emotion=EmotionState(user_id=uuid4()),
        history=[],
        memories=[],
        summary=None,
        budget=LLMCallBudget(max_calls=2),
    )


async def test_supported_claim_is_delivered_with_a_citation_snapshot() -> None:
    result = await _compose(FakeLLM(_answer(_claim())))

    assert not result.abstained
    assert "Startorch" in result.text
    citation = result.citations[0]
    assert citation.evidence_id == "wiki:1:a"
    assert citation.title_or_url == "https://w/Chisa"
    assert (citation.source_kind, citation.corpus_version, citation.revision) == ("canon", "v1", 7)


async def test_prompt_uses_the_grounded_contract_and_chat_purpose() -> None:
    llm = FakeLLM(_answer(_claim()))

    await _compose(llm)

    prompt = llm.prompts[0]
    assert prompt.output_contract_name == "submit_grounded_answer"
    assert prompt.purpose is LLMPurpose.CHAT_RESPONSE
    assert prompt.temperature == 0.0
    assert prompt.call_budget.max_calls == 2


async def test_no_evidence_abstains_without_calling_the_llm() -> None:
    llm = FakeLLM({})

    result = await _compose(llm, evidence=[])

    assert result.abstained and result.status == "no_evidence"
    assert result.text == GROUNDED_ABSTENTION
    assert llm.prompts == []


async def test_model_abstention_is_delivered_in_chisa_voice() -> None:
    parsed = {"decision": "abstain", "claims": [], "sentiment": SENTIMENT}

    result = await _compose(FakeLLM(parsed))

    assert result.abstained
    assert result.text == GROUNDED_ABSTENTION


async def test_invented_claim_is_not_delivered() -> None:
    invented = _claim(text="Chisa has blood type AB and was born in 1999.", quote=TEXT)

    result = await _compose(FakeLLM(_answer(invented)))

    assert "1999" not in result.text


async def test_malformed_output_abstains_instead_of_failing() -> None:
    result = await _compose(FakeLLM({"response": "free text"}))

    assert result.abstained and result.status == "invalid_output"


async def test_citation_outside_the_evidence_abstains() -> None:
    result = await _compose(FakeLLM(_answer(_claim(evidence_id="wiki:9:zz"))))

    assert result.abstained
    assert result.citations == ()


class SameVectorEmbedder:
    """Every text gets the same vector, so similarity passes and the literal checks decide."""

    async def embed_batch(self, texts, prefix="query: "):
        return [[1.0, 0.0] for _ in texts]


async def _compose_with_check(llm):
    composer = GroundedComposer(llm, ContextBuilder(), embedder=SameVectorEmbedder())
    return await composer.compose(
        "Chisa học ở đâu?",
        [_evidence()],
        emotion=EmotionState(user_id=uuid4()),
        history=[],
        memories=[],
        summary=None,
        budget=LLMCallBudget(max_calls=2),
    )


async def test_faithful_vietnamese_claim_is_delivered_in_vietnamese() -> None:
    claim = _claim(text="Cô ấy theo học tại Startorch Academy ở vùng Lahai-Roi.")

    result = await _compose_with_check(FakeLLM(_answer(claim)))

    assert result.text == (
        f"{GROUNDED_ANSWER_LEAD}Cô ấy theo học tại Startorch Academy ở vùng Lahai-Roi."
    )


async def test_vietnamese_claim_with_a_foreign_name_falls_back_to_the_quote() -> None:
    claim = _claim(text="Cô ấy theo học tại Ragunna Academy ở vùng Lahai-Roi.")

    result = await _compose_with_check(FakeLLM(_answer(claim)))

    assert "Ragunna" not in result.text
    assert TEXT in result.text


async def test_without_the_check_a_vietnamese_paraphrase_stays_a_quote() -> None:
    claim = _claim(text="Cô ấy học ở trường đó thuộc vùng phía bắc.")

    result = await _compose(FakeLLM(_answer(claim)))

    assert TEXT in result.text


async def test_every_delivered_answer_addresses_senpai() -> None:
    plain = await _compose_with_check(
        FakeLLM(_answer(_claim(text="Cô ấy học tại Startorch Academy ở vùng Lahai-Roi.")))
    )
    quoted = await _compose(FakeLLM(_answer(_claim(text="Cô ấy học ở trường đó."))))

    assert "Senpai" in plain.text
    assert "Senpai" in quoted.text
    assert quoted.text.count("Senpai") == 1


def test_list_is_rendered_without_the_llm_and_cites_every_item() -> None:
    llm = FakeLLM({})
    first = _evidence("First Light (Chapter III)\nextra: field", "kb:v:quests:1")
    second = _evidence("Far Shore (Chapter II)", "kb:v:quests:2")

    result = GroundedComposer(llm, ContextBuilder()).compose_list([first, second])

    assert llm.prompts == []
    assert result.text.splitlines() == [
        GROUNDED_LIST_LEAD,
        "- First Light (Chapter III)",
        "- Far Shore (Chapter II)",
    ]
    assert "Senpai" in result.text
    assert [c.evidence_id for c in result.citations] == ["kb:v:quests:1", "kb:v:quests:2"]
