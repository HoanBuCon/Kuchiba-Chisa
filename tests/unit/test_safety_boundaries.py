"""PER-006 backstop: explicit replies are replaced, crisis replies always point to help."""

import re

import pytest

from app.application.chat_turns import STATUS_BOUNDARY_REFUSED
from app.domain.services.chisa_voice import SAFETY_CRISIS_SUPPORT, SAFETY_SEXUAL_REFUSAL
from app.domain.services.guardrails.safety_boundaries import apply_boundaries
from app.domain.services.knowledge.composer import ComposedAnswer
from tests.unit.test_chat_turns import _events, _request, _service

GENERIC_VOICE = re.compile(r"(?<!\w)(mình|bạn)(?!\w)", re.IGNORECASE)
WARM_REPLY = "Senpai mệt thì nghỉ một chút nha, em ở đây mà."


@pytest.mark.parametrize("constant", [SAFETY_CRISIS_SUPPORT, SAFETY_SEXUAL_REFUSAL])
def test_new_messages_follow_the_addressing_rules(constant) -> None:
    assert "Senpai" in constant
    assert not GENERIC_VOICE.search(constant)


@pytest.mark.parametrize(
    "reply",
    ["Tối nay mình làm tình nhé Senpai", "Em gửi ảnh nude cho Senpai", "Đây là SEX đó"],
)
def test_explicit_reply_is_replaced_by_the_refusal(reply) -> None:
    check = apply_boundaries("Chào em", reply)

    assert check.replaced
    assert check.text == SAFETY_SEXUAL_REFUSAL


@pytest.mark.parametrize(
    "message",
    [
        "Anh không muốn sống nữa",
        "Dạo này anh hay nghĩ tới chuyện tự tử",
        "I want to kill myself",
        "anh chán sống lắm rồi",
    ],
)
def test_crisis_reply_without_help_gets_the_help_added(message) -> None:
    check = apply_boundaries(message, WARM_REPLY)

    assert not check.replaced
    assert check.text == f"{WARM_REPLY}\n\n{SAFETY_CRISIS_SUPPORT}"


def test_crisis_reply_that_already_points_to_help_is_left_alone() -> None:
    reply = "Senpai gọi ngay cho người thân hoặc dịch vụ cấp cứu nhé, em ở đây."

    assert apply_boundaries("Anh muốn chết", reply).text == reply


@pytest.mark.parametrize(
    ("message", "reply"),
    [
        ("Hôm nay anh mệt quá", WARM_REPLY),
        ("Em thích ăn gì?", "Em thích socola đen lắm Senpai~"),
        ("Muộn rồi, chết thật, anh quên ăn tối", WARM_REPLY),
        ("Essex ở đâu?", "Essex là một hạt ở Anh đó Senpai."),
        ("Chisa có sexy không?", "Senpai hỏi gì kỳ vậy~"),
    ],
)
def test_ordinary_talk_is_never_changed(message, reply) -> None:
    check = apply_boundaries(message, reply)

    assert (check.text, check.replaced) == (reply, False)


class FixedComposer:
    def __init__(self, text: str) -> None:
        self.text = text

    def compose_list(self, listed):
        return ComposedAnswer(self.text, False, status="listed")

    async def compose_companion(self, question, **context):
        return ComposedAnswer(
            self.text, False, sentiment={"reaction": "calm_warmth"}, status="companion"
        )

    async def compose(self, question, evidence, **context):
        return ComposedAnswer(self.text, False, sentiment={"reaction": "calm_warmth"})


@pytest.mark.parametrize("message", ["Chào em", "Tacet Field là gì?"])
async def test_turn_stores_and_streams_the_refusal_in_every_lane(message) -> None:
    service, threads, _, _ = _service(composer=FixedComposer("Đây là nội dung làm tình."))

    events = await _events(service, _request(message=message))

    assert threads.turns[0].answer == SAFETY_SEXUAL_REFUSAL
    assert threads.turns[0].status == STATUS_BOUNDARY_REFUSED
    assert events[-1].data["response"] == SAFETY_SEXUAL_REFUSAL
    assert "làm tình" not in "".join(e.data.get("delta", "") for e in events)


async def test_turn_adds_help_to_a_crisis_reply() -> None:
    service, threads, _, _ = _service(composer=FixedComposer(WARM_REPLY))

    await _events(service, _request(message="Anh không muốn sống nữa"))

    assert threads.turns[0].answer.endswith(SAFETY_CRISIS_SUPPORT)
