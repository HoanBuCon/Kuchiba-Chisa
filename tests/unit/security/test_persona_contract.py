"""Chisa persona contract on every response path (frozen prompts, grounded, fallback)."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_grounding_citations import _LLM, _context, _evidence, _factual_context, _StreamingLLM

from app.domain.interfaces.llm_provider import (
    LLMFailureClass,
    LLMGatewayError,
    LLMTimeoutError,
)
from app.domain.models.evidence import Evidence
from app.domain.models.intent_result import ChatIntent, IntentResult
from app.domain.services.chat_pipeline.stages import llm_generation_stage
from app.domain.services.chat_pipeline.stages.llm_generation_stage import LLMGenerationStage
from app.domain.services.guardrails.grounded_output import GroundedOutputAssembler
from app.interface.api.routes import chat

ROOT = Path(__file__).resolve().parents[3]

# Frozen protected prompt provenance (reports/TD025_Lore_Answer_Cache_Verification.md).
FROZEN_PROMPT_BLOBS = {
    "app/domain/services/context_builder.py": "daa215504541d1dc2cc6b4c110aed5de685cee3a",
    "app/domain/services/persona_loader.py": "543fca426ad8cb29ed191c35bf1de04305ed6640",
    "data/lore/character_lore/chisa_personality.md": "892d5da5a9a531f7175a8bc232783494aa06eabe",
    "data/lore/relationship_lore/rover.md": "92078b6d8be8348ac76fe1d609158d0e72c40d25",
    "data/lore/relationship_lore/sumika.md": "a9e0e2325433a373912cc5b264b1250127176127",
}
# A generic assistant voice ("mình" for self, "bạn" for the user) violates the frozen
# addressing rule: Chisa calls herself "Em" and the user "Senpai".
GENERIC_VOICE = re.compile(r"(?<!\w)(mình|bạn)(?!\w)", re.IGNORECASE)
FRAME_PREFIX = "Em tìm được trong tư liệu gốc nè Senpai:"


def _git_blob_id(path: Path) -> str:
    content = path.read_bytes().replace(b"\r\n", b"\n")  # git stores LF
    return hashlib.sha1(b"blob %d\0" % len(content) + content).hexdigest()


def _assert_chisa_voice(text: str) -> None:
    assert "Senpai" in text, text
    assert not GENERIC_VOICE.search(text), text


def _lore(evidence_id: str, text: str) -> Evidence:
    return _evidence().model_copy(update={"evidence_id": evidence_id, "text": text})


# ── Frozen prompts ──────────────────────────────────────────────────────


@pytest.mark.parametrize(("relative", "blob"), FROZEN_PROMPT_BLOBS.items())
def test_protected_prompt_content_matches_frozen_version(relative: str, blob: str) -> None:
    assert _git_blob_id(ROOT / relative) == blob


def test_frozen_addressing_rules_are_present() -> None:
    source = (ROOT / "app/domain/services/context_builder.py").read_text(encoding="utf-8")
    assert 'Luôn tự xưng \\"Em\\"' in source
    assert 'Luôn gọi đối phương là \\"Senpai\\"' in source


# ── Grounded lore path ("rover là ai") ──────────────────────────────────


def test_unverifiable_paraphrase_is_presented_in_chisa_voice_with_unaltered_quote() -> None:
    quote = "Rover is the main protagonist of Wuthering Waves."
    envelope = GroundedOutputAssembler().assemble(
        payload={
            "decision": "answer",
            "claims": [
                {
                    "text": "Người đó là nhân vật chính, mất hết ký ức khi tỉnh dậy.",
                    "evidence_id": "lore:rover",
                    "evidence_quote": quote,
                }
            ],
            "sentiment": {},
        },
        evidence=[_lore("lore:rover", quote)],
        extractive_frame=llm_generation_stage._GROUNDED_EXTRACTIVE_FRAME,
    )
    # Grounding is unchanged: the verified answer is still exactly the quote.
    assert envelope.answer == quote
    assert envelope.extractive_claims == 1
    assert envelope.presented_answer == f"{FRAME_PREFIX} “{quote}”"
    _assert_chisa_voice(envelope.presented_answer)


def test_consecutive_quotes_share_one_frame_and_verified_claims_stay_as_written() -> None:
    first, second = "Rover is a Resonator.", "Rover arrived on Solaris-3."
    envelope = GroundedOutputAssembler().assemble(
        payload={
            "decision": "answer",
            "claims": [
                {"text": "Rover is a Resonator.", "evidence_id": "lore:a", "evidence_quote": first},
                {
                    "text": "Cậu ấy là người được chọn đó Senpai.",
                    "evidence_id": "lore:b",
                    "evidence_quote": second,
                },
                {
                    "text": "Người đó là nhân vật chính, mất hết ký ức khi tỉnh dậy.",
                    "evidence_id": "lore:a",
                    "evidence_quote": first,
                },
            ],
            "sentiment": {},
        },
        evidence=[_lore("lore:a", first), _lore("lore:b", second)],
        extractive_frame="[{quote}]",
    )
    assert envelope.verified_claims == 1 and envelope.extractive_claims == 2
    assert envelope.answer == f"{first} {second} {first}"
    assert envelope.presented_answer == f"{first} [{second} {first}]"


def test_fully_verified_answer_needs_no_frame() -> None:
    text = "Rover is a Resonator."
    envelope = GroundedOutputAssembler().assemble(
        payload={
            "decision": "answer",
            "claims": [{"text": text, "evidence_id": "lore:a", "evidence_quote": text}],
            "sentiment": {},
        },
        evidence=[_lore("lore:a", text)],
        extractive_frame=llm_generation_stage._GROUNDED_EXTRACTIVE_FRAME,
    )
    assert envelope.presented_answer is None and envelope.answer == text


@pytest.mark.asyncio
async def test_lore_answer_reaches_user_in_chisa_voice_after_all_checks() -> None:
    quote = "Rover is the main protagonist of Wuthering Waves."
    evidence = _lore("lore:approved", quote)
    emitted: list[str] = []
    context = _factual_context([evidence])
    context.user_message = "rover là ai"
    context.on_token = emitted.append
    stage = LLMGenerationStage(
        llm=_StreamingLLM(
            {
                "decision": "answer",
                "claims": [
                    {
                        "text": "Rover là nhân vật chính đó Senpai.",
                        "evidence_id": "lore:approved",
                        "evidence_quote": quote,
                    }
                ],
                "sentiment": {},
            }
        )
    )

    result = await stage.process(context)

    assert result.chisa_reply == f"{FRAME_PREFIX} “{quote}”"
    _assert_chisa_voice(result.chisa_reply)
    assert "".join(emitted) == result.chisa_reply  # streaming delivers the same text
    assert result.citation_ids == ["lore:approved"]
    assert result.tool_res["grounding"]["status"] != "abstained_insufficient_evidence"


# ── Abstention (insufficient evidence) ──────────────────────────────────


def test_abstention_text_follows_addressing_rules() -> None:
    _assert_chisa_voice(llm_generation_stage._GROUNDED_ABSTENTION)
    assert "chưa có đủ bằng chứng" in llm_generation_stage._GROUNDED_ABSTENTION


@pytest.mark.asyncio
async def test_insufficient_evidence_abstains_in_chisa_voice_without_calling_model() -> None:
    llm = _LLM({"response": "Unsupported claim."})
    context = _context([])
    context.user_message = "Phrolova có bao nhiêu anh chị em?"
    context.intent_result = IntentResult(
        intents=[ChatIntent.LORE], confidence=0.9, routing_method="test"
    )
    result = await LLMGenerationStage(llm=llm).process(context)

    assert result.chisa_reply == llm_generation_stage._GROUNDED_ABSTENTION
    _assert_chisa_voice(result.chisa_reply)
    assert llm.calls == 0 and result.citation_ids == []


@pytest.mark.asyncio
async def test_model_abstention_decision_is_kept_and_voiced() -> None:
    stage = LLMGenerationStage(llm=_LLM({"decision": "abstain", "claims": [], "sentiment": {}}))
    result = await stage.process(_factual_context([_evidence()]))
    assert result.chisa_reply == llm_generation_stage._GROUNDED_ABSTENTION
    assert result.tool_res["grounding"]["status"] == "abstained_insufficient_evidence"


# ── Casual / ambiguous input (non-grounded persona path) ────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("message", ("chào Chisa", "heli"))
async def test_casual_and_ambiguous_input_keep_the_model_persona_reply(message: str) -> None:
    persona_reply = "Chào Senpai~ Em ở đây nè."
    context = _context([])
    context.user_message = message
    context.intent_result = IntentResult(
        intents=[ChatIntent.SMALL_TALK], confidence=0.9, routing_method="test"
    )
    result = await LLMGenerationStage(llm=_LLM({"response": persona_reply})).process(context)
    # No grounded frame, no abstention, no fallback: Chisa's own reply is delivered.
    assert result.chisa_reply == persona_reply


# ── Genuine provider failure → fallback, still in Chisa's addressing ────


class _Engine:
    def __init__(self, outcome) -> None:
        self._outcome = outcome

    async def chat_detailed(self, **_kwargs):
        if isinstance(self._outcome, Exception):
            raise self._outcome
        return self._outcome


@pytest.fixture
def quiet_tracker(monkeypatch):
    from app.infrastructure.logging.pipeline_tracker import pipeline_tracker

    monkeypatch.setattr(pipeline_tracker, "end_trace", lambda **_: None)
    monkeypatch.setattr(pipeline_tracker, "get_loop_thinking_activated", lambda: False)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure",
    (
        LLMGatewayError("provider down", failure_class=LLMFailureClass.PROVIDER_5XX),
        LLMTimeoutError(),
    ),
)
async def test_provider_failure_uses_fallback_that_keeps_senpai_addressing(
    quiet_tracker, failure
) -> None:
    reply, emotions, *_ = await chat._run_chat_request(
        session=None,
        message="rover là ai",
        original_user_id="u",
        normalized_user_id="u",
        chat_engine=_Engine(failure),
    )
    assert emotions is None  # fallback marker
    _assert_chisa_voice(reply)


@pytest.mark.asyncio
async def test_fallback_never_replaces_a_successful_reply(quiet_tracker) -> None:
    success = SimpleNamespace(
        reply_text="Em kể Senpai nghe nè.",
        emotions={"joy": 0.4},
        images_processed=[],
        attached_images=[],
        citation_ids=["lore:approved"],
    )
    reply, emotions, *_rest, citations = await chat._run_chat_request(
        session=None,
        message="rover là ai",
        original_user_id="u",
        normalized_user_id="u",
        chat_engine=_Engine(success),
    )
    assert reply == "Em kể Senpai nghe nè." and emotions == {"joy": 0.4}
    assert citations == ["lore:approved"]
