"""Fail-closed corpus safety scan of a cleaned page over the shared guards (SEC-RAG-001)."""

from __future__ import annotations

from hashlib import sha256

from app.domain.ingestion.documents import CanonicalDocument
from app.domain.services.guardrails import CorpusSafetyGate
from app.domain.services.guardrails.pii_redaction import PiiRedactor


class CorpusSafetyPolicy:
    def __init__(
        self, gate: CorpusSafetyGate | None = None, pii: PiiRedactor | None = None
    ) -> None:
        self._gate = gate or CorpusSafetyGate()
        self._pii = pii or PiiRedactor()

    def scan(self, document: CanonicalDocument) -> tuple[str, ...]:
        """Return every rule the page breaks; any finding quarantines it."""
        findings: set[str] = set()
        for block in document.blocks:
            rule = self._rule(block.text, document.page_id)
            if rule:
                findings.add(rule)
            findings.update(f"pii:{name}" for name in self._pii.redact(block.text).categories)
        return tuple(sorted(findings))

    def _rule(self, text: str, page_id: int) -> str | None:
        checksum = sha256(text.encode("utf-8")).hexdigest()
        decision = self._gate.inspect(text=text, source_id=f"page:{page_id}", checksum=checksum)
        return decision.rule_id if decision.quarantined else None
