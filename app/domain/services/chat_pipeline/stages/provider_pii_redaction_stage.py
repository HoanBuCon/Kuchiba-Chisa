"""Minimize PII in a provider-bound prompt without changing stored conversation data."""

from __future__ import annotations

from collections import Counter

from app.domain.services.chat_pipeline.context import ChatContext
from app.domain.services.chat_pipeline.stage import PipelineStage
from app.domain.services.guardrails.pii_redaction import PiiRedactor


class ProviderPiiRedactionStage(PipelineStage):
    """Create a private redacted prompt copy immediately before LLM invocation."""

    def __init__(self, redactor: PiiRedactor | None = None) -> None:
        self._redactor = redactor or PiiRedactor()

    async def process(self, context: ChatContext) -> ChatContext:
        if context.is_cached_answer or context.prompt is None:
            return context

        prompt = context.prompt.model_copy(deep=True)
        counts: Counter[str] = Counter()

        prompt_fields = (
            "system",
            "user_message",
            "history",
            "retrieved_memories",
            "retrieved_lore",
        )
        for field_name in prompt_fields:
            value, field_counts = self._redactor.redact_value(getattr(prompt, field_name))
            setattr(prompt, field_name, value)
            counts.update(field_counts)

        # Evidence is typed and may contain PII in text. Keep provenance IDs and
        # ACL untouched while minimizing its provider-visible content.
        redacted_evidence = []
        for evidence in prompt.retrieved_evidence:
            redacted_text, field_counts = self._redactor.redact_value(evidence.text)
            redacted_evidence.append(evidence.model_copy(update={"text": redacted_text}))
            counts.update(field_counts)
        prompt.retrieved_evidence = redacted_evidence

        context.prompt = prompt
        context.provider_pii_redaction_counts = dict(counts)
        return context
