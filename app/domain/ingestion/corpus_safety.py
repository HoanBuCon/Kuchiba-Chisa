"""Fail-closed corpus safety for a cleaned page over the shared guards (SEC-RAG-001)."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from dataclasses import replace
from hashlib import sha256
from typing import Any

from app.domain.ingestion.documents import Block, CanonicalDocument, GlossaryEntry
from app.domain.models.corpus_safety_exception import ApprovedPageSafetyException
from app.domain.services.guardrails import CorpusSafetyGate
from app.domain.services.guardrails.pii_redaction import PiiRedactor

EMAIL_ONLY = {"email"}


def _strings(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, list | tuple):
        for item in value:
            yield from _strings(item)


def _map_strings(value: Any, transform: Callable[[str], str]) -> Any:
    if isinstance(value, str):
        return transform(value)
    if isinstance(value, dict):
        return {key: _map_strings(item, transform) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return type(value)(_map_strings(item, transform) for item in value)
    return value


def _corpus_texts(document: CanonicalDocument) -> Iterator[str]:
    # Dialogue turns are rendered into block.text, so they need no separate pass.
    for block in document.blocks:
        yield block.text
        if block.title:
            yield block.title
    for entry in document.glossary:
        yield entry.definition
    yield from _strings(document.infoboxes)


class CorpusSafetyPolicy:
    def __init__(
        self,
        gate: CorpusSafetyGate | None = None,
        pii: PiiRedactor | None = None,
        exceptions: Iterable[ApprovedPageSafetyException] = (),
    ) -> None:
        self._gate = gate or CorpusSafetyGate()
        self._pii = pii or PiiRedactor()
        self._exempt = {(e.page_id, e.rule_id, e.content_sha256) for e in exceptions}

    def redact_emails(self, document: CanonicalDocument) -> CanonicalDocument:
        """Mask addresses, which carry no lore; a text with other PII stays intact to be blocked."""
        return replace(
            document,
            blocks=tuple(self._redact_block(block) for block in document.blocks),
            glossary=tuple(
                GlossaryEntry(entry.term, self._without_email(entry.definition))
                for entry in document.glossary
            ),
            infoboxes=_map_strings(document.infoboxes, self._without_email),
        )

    def scan(self, document: CanonicalDocument) -> tuple[str, ...]:
        """Return every rule the page breaks; any finding not exempted quarantines it."""
        findings: set[str] = set()
        for text in _corpus_texts(document):
            rule = self._rule(text, document.page_id)
            if rule:
                findings.add(rule)
            findings.update(f"pii:{name}" for name in self._pii.redact(text).categories)
        return tuple(sorted(findings))

    def vet_infoboxes(
        self, page_id: int, infoboxes: tuple[dict[str, str], ...]
    ) -> tuple[tuple[dict[str, str], ...], tuple[str, ...]]:
        """Masked infobox data and its findings, for pages that skip the silver stage."""
        masked = _map_strings(infoboxes, self._without_email)
        findings: set[str] = set()
        for text in _strings(masked):
            rule = self._rule(text, page_id)
            if rule:
                findings.add(rule)
            findings.update(f"pii:{name}" for name in self._pii.redact(text).categories)
        return masked, tuple(sorted(findings))

    def _redact_block(self, block: Block) -> Block:
        return replace(
            block,
            text=self._without_email(block.text),
            turns=tuple(replace(turn, text=self._without_email(turn.text)) for turn in block.turns),
        )

    def _without_email(self, text: str) -> str:
        result = self._pii.redact(text)
        return result.value if set(result.categories) == EMAIL_ONLY else text

    def _rule(self, text: str, page_id: int) -> str | None:
        checksum = sha256(text.encode("utf-8")).hexdigest()
        decision = self._gate.inspect(text=text, source_id=f"page:{page_id}", checksum=checksum)
        if not decision.quarantined or (page_id, decision.rule_id, checksum) in self._exempt:
            return None
        return decision.rule_id
