"""Verify a paraphrase in another language against its quote, with no extra LLM call (GRD-003).

Term overlap cannot compare Vietnamese with English, and embeddings alone are not safe: a claim
with a swapped name or a negation scores almost like a true one. So names, numbers and negation
are checked literally, and similarity only confirms the claim is about the quote. Calibrated on
224 real claims: 62% of true claims pass, against 13% before; 0% with a wrong quote or number,
1.4% negated, 2.3% with a swapped name (docs/r2-plan.md).
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence

from app.domain.interfaces.embedding_provider import IEmbeddingProvider

MIN_SIMILARITY = 0.80
QUERY_PREFIX = "query: "
# Plain ASCII capitalised words: Vietnamese sentence openers almost always carry diacritics.
_NAME = re.compile(r"\b[A-Z][A-Za-z'’-]{2,}\b")
_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")
# Addressing words and common capitalised Vietnamese words without diacritics are not names.
_NOT_NAMES = frozenset(
    {"Anh", "Ban", "Cha", "Chapter", "Con", "Em", "Hoa", "Khi", "Nhan", "Sau", "Senpai", "Ten"}
    | {"Theo", "Tin", "Trong", "Tuy"}
)
_NEGATION = re.compile(
    r"\b(không|chưa|chẳng|chả|đừng|cấm|not|no|never|cannot|without|none|nothing|neither|nor"
    r"|unable|lack|lacks|unknown)\b|n't\b",
    re.IGNORECASE,
)


def _fold(text: str) -> str:
    return unicodedata.normalize("NFKC", text).casefold()


def facts_match(claim: str, quote: str, evidence: str) -> bool:
    """Every number and name must be in the evidence, and both sides must agree on negation."""
    source = _fold(f"{evidence} {quote}")
    if any(number not in source for number in _NUMBER.findall(claim)):
        return False
    names = (match for match in _NAME.findall(claim) if match not in _NOT_NAMES)
    if any(_fold(name) not in source for name in names):
        return False
    return bool(_NEGATION.search(claim)) == bool(_NEGATION.search(quote))


class CrossLanguageClaimCheck:
    """Similarities are computed up front, because the assembler's verification is synchronous."""

    def __init__(self, similarities: dict[tuple[str, str], float]) -> None:
        self._similarities = similarities

    @classmethod
    async def prepare(
        cls, embedder: IEmbeddingProvider, pairs: Sequence[tuple[str, str]]
    ) -> CrossLanguageClaimCheck:
        texts = sorted({text for pair in pairs for text in pair})
        vectors = await embedder.embed_batch(texts, prefix=QUERY_PREFIX) if texts else []
        by_text = dict(zip(texts, vectors, strict=True))
        return cls({(a, b): _cosine(by_text[a], by_text[b]) for a, b in pairs})

    def __call__(self, claim: str, quote: str, evidence: str) -> bool:
        similarity = self._similarities.get((claim, quote), 0.0)
        return similarity >= MIN_SIMILARITY and facts_match(claim, quote, evidence)


def _cosine(left: Sequence[float], right: Sequence[float]) -> float:
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    norm = (sum(a * a for a in left) * sum(b * b for b in right)) ** 0.5
    return dot / norm if norm else 0.0
