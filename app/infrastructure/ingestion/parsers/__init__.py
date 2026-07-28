"""
Upstream Parsers for the Ingestion Pipeline.

Handles raw wikitext sanitization, table parsing, infobox extraction,
and page type classification (§3 + §5 of Architecture Doc).

Pipeline position: Stage 1–3 (STORE → CLASSIFY → PARSE)

Modules:
    sanitizer      — Regex-based wikitext cleaning (8 ordered operations)
    table_parser   — MediaWiki {| ... |} table extraction to structured dicts
    infobox_parser — Template key-value extraction (infoboxes + general templates)
    classifier     — Rule-based page type classification with confidence scoring
"""

from app.infrastructure.ingestion.parsers.sanitizer import (
    sanitize_wikitext,
    strip_boilerplate_sections,
)
from app.infrastructure.ingestion.parsers.wikitext_parser import (
    convert_wikitext_to_markdown,
)
from app.infrastructure.ingestion.parsers.table_parser import (
    parse_mediawiki_table,
    extract_all_tables,
)
from app.infrastructure.ingestion.parsers.infobox_parser import (
    extract_infobox,
    extract_templates,
)
from app.infrastructure.ingestion.parsers.classifier import (
    classify_page_type,
    ClassificationResult,
)

__all__ = [
    # Sanitizer
    "sanitize_wikitext",
    "strip_boilerplate_sections",
    "convert_wikitext_to_markdown",
    # Table parser
    "parse_mediawiki_table",
    "extract_all_tables",
    # Infobox parser
    "extract_infobox",
    "extract_templates",
    # Classifier
    "classify_page_type",
    "ClassificationResult",
]
