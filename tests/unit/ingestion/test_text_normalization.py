"""ING-012 normalisation: identical on the index and query side."""

import pytest

from app.domain.ingestion.text_normalization import normalize_text


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Thank you, (‍Rover‍).", "Thank you, Rover."),
        ("Café", "Café"),
        ("a  b\t c", "a b c"),
        ("  one \n\n\n\n two  ", "one\n\ntwo"),
        ("soft­hyphen﻿", "softhyphen"),
    ],
)
def test_normalize_text(raw: str, expected: str) -> None:
    assert normalize_text(raw) == expected


def test_query_and_index_agree_on_the_player_name() -> None:
    assert normalize_text("(Rover)") == normalize_text("Rover")
