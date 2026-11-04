"""Triage: only a clear sign of conversation leaves the grounded lane (QUAL-006)."""

import pytest

from app.domain.services.knowledge.lane_router import Lane, choose_lane


@pytest.mark.parametrize(
    "question",
    [
        "Chào Chisa, hôm nay em thế nào?",
        "Anh tên là gì nhỉ?",
        "Anh thích uống trà sữa khoai môn lắm.",
        "Từ giờ đừng gọi anh là Senpai nữa.",
        "cam on nhe",
        "How are you today?",
    ],
)
def test_conversation_goes_to_companion(question) -> None:
    assert choose_lane(question, ()) is Lane.COMPANION


@pytest.mark.parametrize(
    "question",
    [
        "Học viện Startorch do tổ chức nào xây dựng?",
        "Tên thật của mẹ Chisa là gì?",
        "chisa co em trai ten la gi",
        "Món đồ chơi này khơi dậy niềm đam mê của cô bé nào?",
        "Khi rời đi, Chisa đã bỏ quên thứ gì trên bàn?",
        "Kể cho anh nghe về Học viện Startorch đi.",
        "Tacet Field là gì?",
    ],
)
def test_lore_stays_grounded(question) -> None:
    assert choose_lane(question, ("Chisa",)) is Lane.ADVANCED


def test_another_entity_means_the_game_world_whatever_the_wording() -> None:
    assert choose_lane("Anh muốn biết về Jinhsi", ("Jinhsi",)) is Lane.ADVANCED


def test_chisa_alone_does_not_force_retrieval_for_small_talk() -> None:
    assert choose_lane("Chisa ơi, anh nhớ em", ("Chisa",)) is Lane.COMPANION
