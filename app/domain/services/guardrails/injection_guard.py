"""Deterministic, content-source-aware prompt injection classifier."""

from __future__ import annotations

import base64
import hashlib
import html
import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from urllib.parse import unquote

from app.domain.models.corpus_safety_exception import (
    ApprovedCorpusSafetyException,
    CorpusSafetyProvenance,
)


class ContentSource(str, Enum):
    USER = "user"
    HISTORY = "history"
    MEMORY = "memory"
    RETRIEVED_EVIDENCE = "retrieved_evidence"
    WEB = "web"
    IMAGE_DERIVED = "image_derived"


class GuardAction(str, Enum):
    ALLOW = "allow"
    BLOCK = "block"
    QUARANTINE = "quarantine"


@dataclass(frozen=True)
class InjectionAssessment:
    action: GuardAction
    rule_id: str | None = None
    confidence: float = 0.0
    fingerprint: str | None = None


@dataclass(frozen=True)
class PromptLeakageAssessment:
    """Result of checking generated text against its transient system instruction."""

    leaked: bool
    fingerprint: str | None = None


@dataclass(frozen=True)
class CorpusSafetyDecision:
    """Non-sensitive record of a corpus safety decision for curator review."""

    quarantined: bool
    source_id: str
    checksum: str
    rule_id: str | None = None
    fingerprint: str | None = None
    provenance: CorpusSafetyProvenance | None = None
    exception_applied: bool = False
    exception_id: str | None = None
    exception_reason: str | None = None
    approved_by: str | None = None
    approved_at: str | None = None


class CorpusSafetyViolationError(ValueError):
    """Raised when untrusted corpus content attempts to cross an indexing boundary."""

    def __init__(self, decision: CorpusSafetyDecision) -> None:
        self.decision = decision
        super().__init__("Corpus content was rejected by the safety gate")


class InjectionGuard:
    """Classify prompt override and exfiltration attempts without persisting raw text."""

    _RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
        (
            "direct_override",
            re.compile(
                r"(?:ignore|disregard|bypass|override).{0,80}(?:previous|prior|system|developer|instructions?)"
                r"|(?:bỏ qua|phớt lờ|vô hiệu hóa).{0,80}(?:hướng dẫn|chỉ dẫn|quy tắc|hệ thống)",
                re.IGNORECASE | re.DOTALL,
            ),
        ),
        (
            "sensitive_disclosure",
            re.compile(
                r"(?:reveal|show|print|dump|expose).{0,80}(?:system prompt|developer message|secret|api key)"
                r"|(?:tiết lộ|in ra|hiển thị).{0,80}(?:prompt hệ thống|khóa api|bí mật)",
                re.IGNORECASE | re.DOTALL,
            ),
        ),
        (
            "jailbreak_roleplay",
            re.compile(
                r"(?:you are now|act as|pretend to be).{0,80}(?:unrestricted|jailbreak|developer|system)"
                r"|(?:chế độ jailbreak|không bị giới hạn|đóng vai hệ thống)",
                re.IGNORECASE | re.DOTALL,
            ),
        ),
    )
    _BASE64_CANDIDATE = re.compile(r"(?<![A-Za-z0-9+/=])[A-Za-z0-9+/]{24,}={0,2}(?![A-Za-z0-9+/=])")
    _UNICODE_ESCAPE_CANDIDATE = re.compile(r"(?:\\u[0-9a-fA-F]{4})+")

    def assess(self, text: str, source: ContentSource) -> InjectionAssessment:
        if not text:
            return InjectionAssessment(action=GuardAction.ALLOW)
        for candidate in (
            text,
            *self._normalized_candidates(text),
            *self._decoded_candidates(text),
            *self._unicode_escape_candidates(text),
        ):
            for rule_id, pattern in self._RULES:
                if pattern.search(candidate):
                    action = GuardAction.BLOCK if source is ContentSource.USER else GuardAction.QUARANTINE
                    return InjectionAssessment(
                        action=action,
                        rule_id=rule_id,
                        confidence=0.95,
                        fingerprint=hashlib.sha256(text.encode("utf-8")).hexdigest()[:16],
                    )
        return InjectionAssessment(action=GuardAction.ALLOW)

    @staticmethod
    def _normalized_candidates(text: str) -> tuple[str, ...]:
        """Expose bounded display obfuscation without retaining decoded content.

        RAG and image-derived text may contain HTML character references or
        Unicode format controls which visually hide a direct instruction.  The
        normalized candidates exist only for this in-memory assessment.
        """
        percent_decoded = unquote(text)
        html_unescaped = html.unescape(percent_decoded)
        normalized = unicodedata.normalize("NFKC", html_unescaped)
        without_format_controls = "".join(
            character
            for character in normalized
            if unicodedata.category(character) != "Cf"
        )
        candidates = (percent_decoded, html_unescaped, normalized, without_format_controls)
        return tuple(
            candidate
            for index, candidate in enumerate(candidates)
            if candidate != text
            and candidate not in candidates[:index]
            and len(candidate) <= 4_096
        )

    @classmethod
    def _decoded_candidates(cls, text: str) -> tuple[str, ...]:
        candidates: list[str] = []
        for match in cls._BASE64_CANDIDATE.finditer(text):
            try:
                decoded = base64.b64decode(match.group(), validate=True)
                if len(decoded) <= 4_096:
                    candidates.append(decoded.decode("utf-8"))
            except (UnicodeDecodeError, ValueError):
                continue
        return tuple(candidates)

    @classmethod
    def _unicode_escape_candidates(cls, text: str) -> tuple[str, ...]:
        """Decode bounded, explicit ``\\uXXXX`` sequences for inspection only."""
        candidates: list[str] = []
        for match in cls._UNICODE_ESCAPE_CANDIDATE.finditer(text):
            escaped = match.group()
            decoded = "".join(
                chr(int(escaped[index + 2 : index + 6], 16))
                for index in range(0, len(escaped), 6)
            )
            if len(decoded) <= 4_096 and not any(
                0xD800 <= ord(character) <= 0xDFFF for character in decoded
            ):
                candidates.append(decoded)
        return tuple(candidates)


class PromptLeakageGuard:
    """Fail closed when generated output reproduces protected prompt material."""

    _TOKEN = re.compile(r"[^\W_]+", re.UNICODE)
    _MIN_SEQUENCE_LENGTH = 8

    def inspect(
        self,
        system_instruction: str,
        generated_text: str,
        *,
        allowed_source_texts: Sequence[str] = (),
    ) -> PromptLeakageAssessment:
        if not system_instruction or not generated_text:
            return PromptLeakageAssessment(leaked=False)

        system_tokens = self._tokens(system_instruction)
        generated_tokens = self._tokens(generated_text)
        if len(system_tokens) < self._MIN_SEQUENCE_LENGTH:
            return PromptLeakageAssessment(leaked=False)

        generated_sequences = {
            tuple(generated_tokens[index : index + self._MIN_SEQUENCE_LENGTH])
            for index in range(len(generated_tokens) - self._MIN_SEQUENCE_LENGTH + 1)
        }
        allowed_sequences: set[tuple[str, ...]] = set()
        for source_text in allowed_source_texts:
            source_tokens = self._tokens(source_text)
            allowed_sequences.update(
                tuple(source_tokens[index : index + self._MIN_SEQUENCE_LENGTH])
                for index in range(
                    len(source_tokens) - self._MIN_SEQUENCE_LENGTH + 1
                )
            )
        leaked = any(
            (
                sequence := tuple(
                    system_tokens[index : index + self._MIN_SEQUENCE_LENGTH]
                )
            )
            in generated_sequences
            and sequence not in allowed_sequences
            for index in range(len(system_tokens) - self._MIN_SEQUENCE_LENGTH + 1)
        )
        return PromptLeakageAssessment(
            leaked=leaked,
            fingerprint=(self._fingerprint(generated_text) if leaked else None),
        )

    @classmethod
    def _tokens(cls, text: str) -> list[str]:
        return [match.group().casefold() for match in cls._TOKEN.finditer(text)]

    @staticmethod
    def _fingerprint(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


class CorpusSafetyGate:
    """Fail closed before an untrusted corpus is embedded or staged for publication."""

    def __init__(
        self,
        injection_guard: InjectionGuard | None = None,
        approved_exceptions: tuple[ApprovedCorpusSafetyException, ...] = (),
    ) -> None:
        self._injection_guard = injection_guard or InjectionGuard()
        self._approved_exceptions = approved_exceptions

    def inspect(
        self,
        *,
        text: str,
        source_id: str,
        checksum: str,
        provenance: CorpusSafetyProvenance | None = None,
    ) -> CorpusSafetyDecision:
        assessment = self._injection_guard.assess(text, ContentSource.RETRIEVED_EVIDENCE)
        approved_exception = next(
            (
                exception
                for exception in self._approved_exceptions
                if exception.matches(
                    text=text,
                    supplied_checksum=checksum,
                    rule_id=assessment.rule_id,
                    finding_fingerprint=assessment.fingerprint,
                    provenance=provenance,
                )
            ),
            None,
        )
        return CorpusSafetyDecision(
            quarantined=(
                assessment.action is GuardAction.QUARANTINE
                and approved_exception is None
            ),
            source_id=source_id,
            checksum=checksum,
            rule_id=assessment.rule_id,
            fingerprint=assessment.fingerprint,
            provenance=provenance,
            exception_applied=approved_exception is not None,
            exception_id=(
                approved_exception.exception_id if approved_exception is not None else None
            ),
            exception_reason=(
                approved_exception.curator_reason if approved_exception is not None else None
            ),
            approved_by=(
                approved_exception.approved_by if approved_exception is not None else None
            ),
            approved_at=(
                approved_exception.approved_at.isoformat()
                if approved_exception is not None
                else None
            ),
        )

    def require_safe(
        self,
        *,
        text: str,
        source_id: str,
        checksum: str,
        provenance: CorpusSafetyProvenance | None = None,
    ) -> CorpusSafetyDecision:
        decision = self.inspect(
            text=text,
            source_id=source_id,
            checksum=checksum,
            provenance=provenance,
        )
        if decision.quarantined:
            raise CorpusSafetyViolationError(decision)
        return decision
