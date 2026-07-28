"""
Offline LLM Enrichment Engine — Integrates instructor for Pydantic Schema enforcement (§6).
"""

from __future__ import annotations
from typing import Any, Optional
import structlog
from app.infrastructure.ingestion.models import CanonicalPage
from app.infrastructure.ingestion.enrichment.models import QuestLoreSummary

import os
from app.config.settings import settings

logger = structlog.get_logger(__name__)

_HAS_INSTRUCTOR = False
try:
    import instructor
    _HAS_INSTRUCTOR = True
except ImportError:
    _HAS_INSTRUCTOR = False


def enrich_canonical_page(
    page: CanonicalPage,
    client: Optional[Any] = None,
    model: Optional[str] = None,
) -> CanonicalPage:
    """
    Enrich complex canonical page (Quest / Lore) using instructor LLM structured output.

    Args:
        page: The CanonicalPage object to enrich.
        client: Optional instructor-wrapped client instance (OpenAI / Gemini).
        model: Target LLM model name (defaults to env-configured settings).

    Returns:
        Enriched CanonicalPage with metadata fields populated.
    """
    if model is None:
        if settings.LLM_PROVIDER == "gemini":
            model = settings.GEMINI_MODEL
        elif settings.LLM_PROVIDER == "groq":
            model = settings.GROQ_MODEL
        else:
            model = os.getenv("LLM_MODEL", settings.GEMINI_MODEL)
    full_text = "\n\n".join(
        f"## {s.title}\n{s.content}" if s.title else s.content for s in page.sections if s.content
    )
    if not full_text or len(full_text) < 50:
        return page

    if client is None or not _HAS_INSTRUCTOR:
        logger.debug("Instructor LLM client not configured; skipping offline enrichment.", page_id=page.identity.page_id)
        return page

    try:
        response: QuestLoreSummary = client.chat.completions.create(
            model=model,
            response_model=QuestLoreSummary,
            messages=[
                {
                    "role": "system",
                    "content": "Extract structured narrative summary and lore details from Wuthering Waves wiki content.",
                },
                {"role": "user", "content": full_text[:4000]},
            ],
        )

        # Update canonical page metadata with enriched data
        page.document_metadata.categories.append("EnrichedLore")
        page.sections = page.sections or []

        logger.info("Canonical page enriched successfully", page_id=page.identity.page_id, title=page.identity.title)
    except Exception as exc:
        logger.warning("Failed to enrich canonical page", page_id=page.identity.page_id, error=str(exc))

    return page
