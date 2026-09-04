"""Deterministic sparse lexical encoder for the Qdrant lore index."""

from __future__ import annotations

import math
import re

import mmh3
from qdrant_client.http.models import SparseVector


class SparseTextEncoder:
    """Hash multilingual tokens into a stable sparse vector; Qdrant applies IDF."""

    _TOKEN_PATTERN = re.compile(r"[\wÀ-ỹ]+", re.UNICODE)

    def encode(self, text: str) -> SparseVector:
        tokens = [token.lower() for token in self._TOKEN_PATTERN.findall(text) if len(token) > 1]
        if not tokens:
            return SparseVector(indices=[], values=[])

        frequencies: dict[int, int] = {}
        for token in tokens:
            index = mmh3.hash(token, signed=False)
            frequencies[index] = frequencies.get(index, 0) + 1

        indices = sorted(frequencies)
        values = [1.0 + math.log(frequencies[index]) for index in indices]
        return SparseVector(indices=indices, values=values)
