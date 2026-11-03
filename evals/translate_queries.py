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
from app.infrastructure.knowledge.llm_query_translator import translation_prompt
from app.infrastructure.llm.gateway_factory import build_llm_gateway
from evals.dataset import GoldenCase, Language, load_golden_set
from evals.retrieval import GOLDEN_PATH, TRANSLATIONS_PATH, load_translations

HTTP_TIMEOUT_SECONDS = 30


def needs_translation(case: GoldenCase, stored: dict[str, str]) -> bool:
    return bool(case.relevant_pages) and case.language != Language.EN and case.id not in stored


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
            response = await gateway.generate(translation_prompt(question))
            stored[case.id] = response.parsed["query"]
            _save(TRANSLATIONS_PATH, stored)
    sys.stdout.write(f"translated {len(pending)}, stored {len(stored)}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
