"""
Wikitext-to-Markdown Parser Module — Converts MediaWiki markup into clean Markdown.

Uses pypandoc as the primary conversion engine with seamless fallback to
custom regex-based converter when Pandoc CLI is unavailable.
"""

from __future__ import annotations
import structlog
from app.infrastructure.ingestion.parsers.sanitizer import wikitext_to_markdown as regex_wikitext_to_markdown

logger = structlog.get_logger(__name__)

_HAS_PYPANDOC = False
try:
    import pypandoc
    _HAS_PYPANDOC = True
except ImportError:
    _HAS_PYPANDOC = False


import re

_RE_MARKDOWN_HEADER = re.compile(r"^\s*#{1,6}\s+\S", re.MULTILINE)
_RE_MEDIAWIKI_HEADER = re.compile(r"^\s*={1,6}\s+[^=]", re.MULTILINE)


def convert_wikitext_to_markdown(text: str, *, force_regex: bool = False) -> str:
    """
    Convert MediaWiki wikitext string to clean Markdown formatting.

    Args:
        text: Input wikitext string (preferably pre-sanitized).
        force_regex: If True, bypass Pandoc and use regex conversion engine.

    Returns:
        Converted clean Markdown string.
    """
    if not text or not text.strip():
        return ""

    # If text is already pure Markdown (has # headers and no == wikitext headers), return directly
    if _RE_MARKDOWN_HEADER.search(text) and not _RE_MEDIAWIKI_HEADER.search(text):
        return text.strip()

    if _HAS_PYPANDOC and not force_regex:
        try:
            converted = pypandoc.convert_text(text, "markdown", format="mediawiki")
            if converted and converted.strip():
                return converted.strip()
        except OSError:
            logger.debug("Pandoc binary CLI not found on system PATH; using fallback regex engine.")
        except Exception as exc:
            logger.warning("pypandoc conversion failed; falling back to regex", error=str(exc))

    return regex_wikitext_to_markdown(text)
