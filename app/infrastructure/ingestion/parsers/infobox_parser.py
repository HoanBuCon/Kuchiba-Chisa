"""
Infobox & Template Parser — Extract structured key-value data from wiki templates.

Implements §3.2 Stage 2 (Template Expansion/Stripping) of the Architecture Doc.

MediaWiki templates look like::

    {{Character Infobox
    |name       = Kuchiba Chisa
    |element    = Spectro
    |weapon     = Sword
    |rarity     = 5
    |region     = Lahai-Roi
    |birthday   = October 6
    }}

Strategy (from architecture recommendation):
    Parse templates to metadata (key-value extraction), then strip the template
    markup from the body text. Store the extracted template data in the page-level
    metadata.

This module uses ``mwparserfromhell`` (already in requirements.txt) for robust
template extraction, with a regex fallback for environments where the library
is unavailable.

Design:
    - Pure functions, no state.
    - Returns clean dicts with stripped values.
    - Handles nested templates gracefully.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

import structlog

logger = structlog.get_logger(__name__)


# ─────────────────────────────────────────────────────────────
# Known infobox template name patterns
# ─────────────────────────────────────────────────────────────

# Lowercase patterns that indicate an infobox template.
# Matches case-insensitively against template name.
INFOBOX_PATTERNS: Tuple[str, ...] = (
    "infobox",
    "character infobox",
    "weapon infobox",
    "echo infobox",
    "item infobox",
    "boss infobox",
    "npc infobox",
    "quest infobox",
    "region infobox",
    "faction infobox",
    "enemy infobox",
)

# Regex fallback patterns (when mwparserfromhell is unavailable)
_RE_TEMPLATE_BLOCK = re.compile(
    r"\{\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}\}",
    re.DOTALL,
)
_RE_TEMPLATE_PARAM = re.compile(r"\|([^|=]+)=([^|]*)")


# ─────────────────────────────────────────────────────────────
# Core extraction using mwparserfromhell
# ─────────────────────────────────────────────────────────────


def _extract_with_mwparser(wikitext: str) -> Tuple[Dict[str, Any], List[Dict[str, Any]], str]:
    """
    Extract infobox and templates using mwparserfromhell.

    Returns:
        Tuple of (infobox_dict, templates_list, infobox_template_name).
    """
    import mwparserfromhell

    wikicode = mwparserfromhell.parse(wikitext)
    templates = wikicode.filter_templates()

    infobox: Dict[str, Any] = {}
    infobox_name: str = ""
    other_templates: List[Dict[str, Any]] = []

    for template in templates:
        t_name = str(template.name).strip()
        t_name_lower = t_name.lower()

        # Extract parameters as dict
        params: Dict[str, str] = {}
        for param in template.params:
            key = str(param.name).strip()
            value = str(param.value).strip()
            if key and value:
                params[key] = value

        # Check if it's an infobox
        is_infobox = any(
            pattern in t_name_lower for pattern in INFOBOX_PATTERNS
        )

        if is_infobox:
            infobox.update(params)
            infobox_name = t_name
            logger.debug(
                "infobox_extracted",
                template_name=t_name,
                param_count=len(params),
            )
        else:
            if params or t_name:
                other_templates.append({
                    "name": t_name,
                    "params": params,
                })

    return infobox, other_templates, infobox_name


def _extract_with_regex(wikitext: str) -> Tuple[Dict[str, Any], List[Dict[str, Any]], str]:
    """
    Fallback extraction using regex when mwparserfromhell is unavailable.

    Less robust than mwparserfromhell but handles most common cases.

    Returns:
        Tuple of (infobox_dict, templates_list, infobox_template_name).
    """
    infobox: Dict[str, Any] = {}
    infobox_name: str = ""
    other_templates: List[Dict[str, Any]] = []

    # Find template blocks
    for match in _RE_TEMPLATE_BLOCK.finditer(wikitext):
        block = match.group(1)
        lines = block.strip().split("\n")

        if not lines:
            continue

        # First line (or part before first |) is the template name
        t_name = lines[0].split("|")[0].strip()
        t_name_lower = t_name.lower()

        # Extract key=value parameters
        params: Dict[str, str] = {}
        full_block = match.group(1)
        for param_match in _RE_TEMPLATE_PARAM.finditer(full_block):
            key = param_match.group(1).strip()
            value = param_match.group(2).strip()
            if key and value:
                params[key] = value

        is_infobox = any(
            pattern in t_name_lower for pattern in INFOBOX_PATTERNS
        )

        if is_infobox:
            infobox.update(params)
            infobox_name = t_name
        else:
            if params or t_name:
                other_templates.append({
                    "name": t_name,
                    "params": params,
                })

    return infobox, other_templates, infobox_name


# ─────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────


def extract_infobox(
    wikitext: str,
    *,
    page_id: Optional[int] = None,
) -> Tuple[Dict[str, Any], str]:
    """
    Extract the infobox template data from raw wikitext.

    Tries ``mwparserfromhell`` first (robust), falls back to regex.

    Args:
        wikitext: Raw MediaWiki wikitext content.
        page_id: Optional page ID for structured log context.

    Returns:
        Tuple of:
            - Dict of infobox key-value pairs (cleaned).
            - Infobox template name (e.g., "Character Infobox").

    Example::

        wikitext = '{{Character Infobox|name=Chisa|element=Spectro}}'
        data, name = extract_infobox(wikitext)
        # data = {"name": "Chisa", "element": "Spectro"}
        # name = "Character Infobox"
    """
    log_ctx = {"page_id": page_id} if page_id else {}

    if not wikitext:
        return {}, ""

    try:
        infobox, _, infobox_name = _extract_with_mwparser(wikitext)
        logger.debug(
            "infobox_extraction_complete",
            method="mwparserfromhell",
            fields=len(infobox),
            template_name=infobox_name,
            **log_ctx,
        )
        return infobox, infobox_name

    except ImportError:
        logger.info("mwparserfromhell_not_available_using_regex_fallback")
        infobox, _, infobox_name = _extract_with_regex(wikitext)
        logger.debug(
            "infobox_extraction_complete",
            method="regex_fallback",
            fields=len(infobox),
            template_name=infobox_name,
            **log_ctx,
        )
        return infobox, infobox_name

    except Exception as exc:
        logger.warning(
            "infobox_extraction_failed",
            error=str(exc),
            **log_ctx,
        )
        return {}, ""


def extract_templates(
    wikitext: str,
    *,
    page_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    Extract all non-infobox templates from raw wikitext.

    Returns templates as a list of dicts with ``name`` and ``params`` fields.
    Infobox templates are excluded (use ``extract_infobox()`` instead).

    Args:
        wikitext: Raw MediaWiki wikitext content.
        page_id: Optional page ID for structured log context.

    Returns:
        List of template dicts: ``[{"name": "...", "params": {...}}, ...]``

    Example::

        templates = extract_templates(wikitext)
        # [{"name": "article-table", "params": {}},
        #  {"name": "Color", "params": {"1": "red"}}]
    """
    log_ctx = {"page_id": page_id} if page_id else {}

    if not wikitext:
        return []

    try:
        _, templates, _ = _extract_with_mwparser(wikitext)
    except ImportError:
        _, templates, _ = _extract_with_regex(wikitext)
    except Exception as exc:
        logger.warning(
            "template_extraction_failed",
            error=str(exc),
            **log_ctx,
        )
        return []

    logger.debug(
        "templates_extracted",
        count=len(templates),
        names=[t["name"] for t in templates[:10]],
        **log_ctx,
    )
    return templates
