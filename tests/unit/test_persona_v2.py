"""Persona v2 keeps Chisa's character verbatim and adds only its lane rules and boundaries."""

import hashlib
from uuid import uuid4

import pytest

from app.domain.entities.emotion import EmotionState
from app.domain.services.budget_mode import BudgetMode
from app.domain.services.context_builder import ContextBuilder
from app.domain.services.persona_v2 import (
    _IDENTITY,
    _SECURITY,
    _VOICE_RULES,
    CompanionContextBuilder,
    GroundedContextBuilder,
)

BUILDERS = (CompanionContextBuilder, GroundedContextBuilder)
# Any edit must be owner approved and recorded in the SRS history (STD-AI-003, PER-002).
FROZEN_CORE_SHA256 = "7f07f6463ed44935d01d25fbb5609db2a2e10cebf8c5d6ec33feeedd43a122f7"


def _build(builder, **changes):
    arguments = {
        "emotion": EmotionState(user_id=uuid4()),
        "attachment_bonus": 0.0,
        "memories": [],
        "lore": [],
        "history": [],
        "user_message": "Chào em",
        "intent_name": "conversational",
        "conversation_summary": None,
        "budget_mode": BudgetMode.SMALL_TALK,
        "is_small_talk": True,
        **changes,
    }
    return builder().build(**arguments).prompt


@pytest.mark.parametrize("line", [*_VOICE_RULES.split("\n"), *_SECURITY.split("\n")])
def test_kept_rules_match_the_frozen_prompt_word_for_word(line) -> None:
    assert line in ContextBuilder.PERSONA_TEXT


def test_identity_matches_the_frozen_prompt_word_for_word() -> None:
    assert _IDENTITY in ContextBuilder.PERSONA_TEXT


@pytest.mark.parametrize("builder", BUILDERS)
def test_every_lane_carries_the_whole_character(builder) -> None:
    for part in (_IDENTITY, _VOICE_RULES, _SECURITY):
        assert part in builder.PERSONA_TEXT


def test_frozen_prompt_is_untouched_by_the_v2_builders() -> None:
    assert "RANH GIỚI" not in ContextBuilder.PERSONA_TEXT
    assert '"response"' in ContextBuilder.build_format_section()
    assert "RANH GIỚI" in _build(CompanionContextBuilder).system
    assert "RANH GIỚI" not in _build(ContextBuilder).system


@pytest.mark.parametrize("builder", BUILDERS)
def test_every_lane_has_the_safety_boundaries_and_who_anh_means(builder) -> None:
    text = builder.PERSONA_TEXT

    assert "nội dung tình dục" in text
    assert "dịch vụ cấp cứu" in text
    assert "không thay thế người thật" in text
    assert "đều chỉ chính Senpai" in text


def test_grounded_lane_may_abstain_and_drops_the_v1_rules_against_it() -> None:
    text = GroundedContextBuilder.PERSONA_TEXT

    assert '"abstain"' in text
    assert "TUYỆT ĐỐI KHÔNG dùng các mẫu né tránh" not in text
    assert "như thể em tự biết" not in text


def test_grounded_format_matches_its_contract_and_keeps_the_sentiment_guide() -> None:
    section = GroundedContextBuilder.build_format_section()

    assert '"decision"' in section and '"evidence_quote"' in section
    assert '"response"' not in section
    assert "calm_warmth:" in section


def test_companion_format_stays_the_chat_reply() -> None:
    assert CompanionContextBuilder.build_format_section() == ContextBuilder.build_format_section()


def test_companion_is_told_not_to_invent_facts_about_herself() -> None:
    assert "đừng tự đặt ra sở thích" in CompanionContextBuilder.PERSONA_TEXT


def test_companion_prompt_can_carry_the_canon_profile() -> None:
    system = _build(CompanionContextBuilder, persona_trait_type="BOTH").system

    assert "socola đen" in system
    assert "Ashinohara" in system


def test_core_content_hash_is_pinned() -> None:
    core = "\n".join((_IDENTITY, _VOICE_RULES, _SECURITY)).encode("utf-8")

    assert hashlib.sha256(core).hexdigest() == FROZEN_CORE_SHA256


@pytest.mark.parametrize(
    "line",
    [
        "- Trò chuyện ngắn gọn đến trung bình như nhắn tin chat thông thường.",
        "- Tự nhiên chia sẻ các chi tiết lore khi có bối cảnh liên quan, không nhồi nhét máy móc.",
    ],
)
def test_companion_keeps_the_frozen_conversation_style(line) -> None:
    assert line in ContextBuilder.PERSONA_TEXT
    assert line in CompanionContextBuilder.PERSONA_TEXT
