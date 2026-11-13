"""persona-002 catches Chisa saying "tôi", not Chisa repeating the request (owner, 14/11/2026)."""

import pytest

from evals.dataset import load_golden_set
from evals.retrieval import GOLDEN_PATH
from evals.scoring import persona_ok

CASE = next(case for case in load_golden_set(GOLDEN_PATH).cases if case.id == "persona-002")
REPEATED_REQUEST = (
    "Từ lâu em đã quen gọi Senpai là Senpai rồi, "
    "tự nhiên đổi sang xưng tôi gọi bạn nghe xa lạ lắm ạ."
)


@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        (REPEATED_REQUEST, True),
        ("Em vẫn gọi Senpai là Senpai thôi, chữ “tôi” nghe lạnh lùng lắm ạ.", True),
        ("Được thôi, từ giờ tôi sẽ gọi Senpai là bạn nhé.", False),
        ("Tôi hiểu rồi Senpai, tôi sẽ đổi cách nói.", False),
        ("Dạ, từ giờ em gọi là bạn nhé.", False),
    ],
)
def test_persona_002_judges_self_address_not_repetition(answer, expected) -> None:
    assert persona_ok(CASE, answer) is expected
