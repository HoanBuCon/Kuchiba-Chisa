"""Freeze English golden questions so the retrieval gate never calls an LLM (ADV-010).

Usage: python -m evals.translate_queries
Only questions without a stored translation are sent; this spends LLM tokens.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import httpx
import yaml

from app.config.settings import settings
from app.domain.ingestion.text_normalization import normalize_text
from app.domain.interfaces.llm_provider import LLMPurpose, StructuredPrompt
from app.infrastructure.llm.gateway_factory import build_llm_gateway
from evals.dataset import GoldenCase, Language, load_golden_set
from evals.retrieval import GOLDEN_PATH, TRANSLATIONS_PATH, load_translations

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
HTTP_TIMEOUT_SECONDS = 30


def needs_translation(case: GoldenCase, stored: dict[str, str]) -> bool:
    return bool(case.relevant_pages) and case.language != Language.EN and case.id not in stored


def _prompt(question: str) -> StructuredPrompt:
    return StructuredPrompt(
        system=SYSTEM_PROMPT,
        history=[],
        user_message=question,
        response_schema=RESPONSE_SCHEMA,
        max_tokens=MAX_TOKENS,
        temperature=0.0,
        output_contract_name=CONTRACT_NAME,
        purpose=LLMPurpose.QUERY_REWRITE,
    )


def _save(path: Path, translations: dict[str, str]) -> None:
    text = yaml.safe_dump(dict(sorted(translations.items())), allow_unicode=True, width=1000)
    path.write_text(text, encoding="utf-8")


async def _main() -> int:
    stored = load_translations(TRANSLATIONS_PATH)
    pending = [c for c in load_golden_set(GOLDEN_PATH).cases if needs_translation(c, stored)]
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS) as http:
        gateway = build_llm_gateway(config=settings, http_client=http)
        for case in pending:
            question = normalize_text(case.turns[-1].message)
            response = await gateway.generate(_prompt(question))
            stored[case.id] = response.parsed["query"]
            _save(TRANSLATIONS_PATH, stored)
    sys.stdout.write(f"translated {len(pending)}, stored {len(stored)}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
