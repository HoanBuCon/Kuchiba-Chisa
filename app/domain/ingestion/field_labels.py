"""Readable labels for infobox keys, so profile cards never expose raw field names (ING-004)."""

from __future__ import annotations

import re

_WORD_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])|[_\-\s]+")

# Keys whose generic split reads poorly: abbreviations and language codes.
_FIXED_LABELS = {
    "voiceEN": "English voice actor",
    "voiceJP": "Japanese voice actor",
    "voiceKR": "Korean voice actor",
    "voiceCN": "Chinese voice actor",
    "id": "ID",
}


def field_label(key: str) -> str:
    """Map an infobox key to an English label; unknown keys are split on camelCase."""
    fixed = _FIXED_LABELS.get(key)
    if fixed:
        return fixed
    words = [word for word in _WORD_BOUNDARY.split(key.strip()) if word]
    if not words:
        return key
    label = " ".join(word if word.isupper() else word.lower() for word in words)
    return label[0].upper() + label[1:]
