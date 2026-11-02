"""Text normalisation shared by indexing and querying so both sides match (ING-012, ADV-002)."""

from __future__ import annotations

import re
import unicodedata

PLAYER_NAME = "Rover"
_ZERO_WIDTH = re.compile("[​‌‍⁠﻿­]")
_SPACES = re.compile(r"[ \t   ]+")
_BLANK_LINES = re.compile(r"\n\s*\n+")
# The wiki writes the player name as "(Rover)" or a raw "{PlayerName}"; both read as the name.
_NAME_PLACEHOLDER = re.compile(rf"\(\s*{PLAYER_NAME}\s*\)|\{{PlayerName\}}")


def normalize_text(text: str) -> str:
    """NFC, no zero-width characters, collapsed spacing, bare player-name placeholder."""
    text = unicodedata.normalize("NFC", _ZERO_WIDTH.sub("", text))
    text = _NAME_PLACEHOLDER.sub(PLAYER_NAME, text)
    lines = (_SPACES.sub(" ", line).strip() for line in text.split("\n"))
    return _BLANK_LINES.sub("\n\n", "\n".join(lines)).strip()
