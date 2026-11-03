"""English search query through the LLM gateway, cached by question (ADV-009, ADV-010)."""

from __future__ import annotations

import hashlib

from app.domain.interfaces.cache_provider import ICacheProvider
from app.domain.interfaces.llm_provider import (
    BaseLLMAdapter,
    LLMCallBudget,
    LLMError,
    LLMPurpose,
    StructuredPrompt,
)
from app.domain.services.knowledge.lore_search import QueryTranslationError

SYSTEM_PROMPT = (
    "Translate the user's question about the game Wuthering Waves into natural English for a wiki "
    "search. The input may be Vietnamese without diacritics or slang. Keep proper nouns unchanged. "
    "Do not answer it. If it is already English, return it unchanged."
)
RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {"query": {"type": "string"}},
    "required": ["query"],
}
CONTRACT_NAME = "query_translation"
MAX_TOKENS = 120
CACHE_PREFIX = "query_translation:v1:"
CACHE_SECONDS = 7 * 24 * 3600


def translation_prompt(question: str, budget: LLMCallBudget | None = None) -> StructuredPrompt:
    prompt = StructuredPrompt(
        system=SYSTEM_PROMPT,
        history=[],
        user_message=question,
        response_schema=RESPONSE_SCHEMA,
        max_tokens=MAX_TOKENS,
        temperature=0.0,
        output_contract_name=CONTRACT_NAME,
        purpose=LLMPurpose.QUERY_REWRITE,
    )
    if budget is not None:
        prompt.call_budget = budget
    return prompt


class LlmQueryTranslator:
    def __init__(self, llm: BaseLLMAdapter, cache: ICacheProvider | None = None) -> None:
        self._llm = llm
        self._cache = cache

    async def to_english(self, question: str, budget: LLMCallBudget | None = None) -> str:
        key = CACHE_PREFIX + hashlib.sha256(question.encode("utf-8")).hexdigest()
        if self._cache is not None:
            cached = await self._cache.get(key)
            if cached:
                return cached
        try:
            response = await self._llm.generate(translation_prompt(question, budget))
        except LLMError as error:
            raise QueryTranslationError(type(error).__name__) from error
        query = response.parsed.get("query")
        if not isinstance(query, str) or not query.strip():
            raise QueryTranslationError("empty translation")
        if self._cache is not None:
            await self._cache.set(key, query, ttl=CACHE_SECONDS)
        return query
