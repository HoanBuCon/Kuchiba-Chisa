"""Deterministic PII/secret minimization before an external provider boundary."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PiiRedactionResult:
    value: str
    categories: dict[str, int]

    @property
    def changed(self) -> bool:
        return bool(self.categories)


class PiiRedactor:
    """Mask high-confidence identifiers without retaining a reversible mapping.

    The implementation intentionally favours precision over speculative entity
    detection. It is a minimization control, not an authorization mechanism.
    """

    _EMAIL = re.compile(r"(?<![\w.+-])[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}(?![\w.-])", re.I)
    _IPV4 = re.compile(
        r"(?<![\d.])(?:25[0-5]|2[0-4]\d|1?\d?\d)"
        r"(?:\.(?:25[0-5]|2[0-4]\d|1?\d?\d)){3}(?![\d.])"
    )
    _PHONE = re.compile(r"(?<!\d)(?:\+?84|0)(?:[ .-]?\d){8,10}(?!\d)")
    _VIETNAM_ID = re.compile(r"(?<!\d)\d{12}(?!\d)")
    _CARD = re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")
    _SECRET = re.compile(
        r"\b(?:api[_-]?key|secret|token|password)\s*[:=]\s*['\"]?([A-Za-z0-9_\-.]{12,})",
        re.I,
    )

    def redact(self, value: str) -> PiiRedactionResult:
        counts: Counter[str] = Counter()

        def replace(pattern: re.Pattern[str], category: str, text: str) -> str:
            def matcher(match: re.Match[str]) -> str:
                if category == "payment_card" and not self._is_luhn_valid(match.group()):
                    return match.group()
                counts[category] += 1
                return f"[REDACTED_{category.upper()}]"

            return pattern.sub(matcher, text)

        result = value
        result = replace(self._SECRET, "secret", result)
        result = replace(self._EMAIL, "email", result)
        result = replace(self._IPV4, "ip_address", result)
        result = replace(self._PHONE, "phone", result)
        result = replace(self._VIETNAM_ID, "national_id", result)
        result = replace(self._CARD, "payment_card", result)
        return PiiRedactionResult(value=result, categories=dict(counts))

    def redact_value(self, value: Any) -> tuple[Any, dict[str, int]]:
        """Return a redacted copy of allowed prompt-shaped data, never mutate input."""
        if isinstance(value, str):
            result = self.redact(value)
            return result.value, result.categories
        if isinstance(value, list):
            redacted: list[Any] = []
            aggregate: Counter[str] = Counter()
            for item in value:
                item_value, counts = self.redact_value(item)
                redacted.append(item_value)
                aggregate.update(counts)
            return redacted, dict(aggregate)
        if isinstance(value, dict):
            redacted_dict: dict[Any, Any] = {}
            aggregate = Counter[str]()
            for key, item in value.items():
                item_value, counts = self.redact_value(item)
                redacted_dict[key] = item_value
                aggregate.update(counts)
            return redacted_dict, dict(aggregate)
        return value, {}

    @staticmethod
    def _is_luhn_valid(candidate: str) -> bool:
        digits = "".join(character for character in candidate if character.isdigit())
        if not 13 <= len(digits) <= 19:
            return False
        checksum = 0
        for index, character in enumerate(reversed(digits)):
            number = int(character)
            if index % 2:
                number *= 2
                if number > 9:
                    number -= 9
            checksum += number
        return checksum % 10 == 0
