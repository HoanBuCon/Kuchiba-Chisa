"""
Page Type Classifier — Rule-based classification with confidence scoring.

Implements §5.1 (Page Type Classification) of the Architecture Document.

Classification sources in priority order:
    1. Wiki categories (from API metadata)  — Most reliable
    2. Infobox template name               — High confidence
    3. Title heuristics                     — Medium confidence
    4. Content heuristics                   — Lower confidence
    5. LLM classification (not here)        — Fallback (handled upstream)

This module handles sources 1–4 (deterministic, zero-cost).
Source 5 (LLM) is handled by the hybrid pipeline controller.

Design:
    - Pure function, no state, no I/O.
    - Returns ClassificationResult with type + confidence + source.
    - Confidence thresholds:
        >= 0.7: Parser-only path (no LLM needed)
        < 0.7:  LLM fallback triggered
"""

from __future__ import annotations

import re
from typing import FrozenSet, List, Optional, Tuple

import structlog
from pydantic import BaseModel, ConfigDict, Field

from app.infrastructure.ingestion.models.canonical_page import PageTypeEnum

logger = structlog.get_logger(__name__)


# ─────────────────────────────────────────────────────────────
# Classification result model
# ─────────────────────────────────────────────────────────────


class ClassificationResult(BaseModel):
    """
    Result of page type classification with confidence and provenance.

    Confidence interpretation:
        >= 0.9: Very high confidence (direct category or infobox match)
        >= 0.7: High confidence (strong heuristic match, no LLM needed)
        >= 0.5: Medium confidence (weak match, LLM validation recommended)
        <  0.5: Low confidence (guessing, LLM fallback required)
    """

    model_config = ConfigDict(extra="ignore")

    page_type: PageTypeEnum = Field(
        ...,
        description="Classified page type.",
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Classification confidence (0.0–1.0).",
    )
    source: str = Field(
        ...,
        description="Classification source: 'category', 'infobox', 'title', 'heuristic'.",
    )
    matched_rule: str = Field(
        default="",
        description="Specific rule/pattern that triggered the classification.",
    )
    is_skip: bool = Field(
        default=False,
        description="Whether this page should be skipped (redirect, disambiguation, etc.).",
    )
    skip_reason: Optional[str] = Field(
        default=None,
        description="Reason for skipping if is_skip is True.",
    )


# ─────────────────────────────────────────────────────────────
# Category → PageType mapping rules
# ─────────────────────────────────────────────────────────────

# Each tuple: (set_of_lowercase_category_keywords, PageTypeEnum, confidence)
# First match wins (rules are ordered by specificity).
_CATEGORY_RULES: List[Tuple[FrozenSet[str], PageTypeEnum, float]] = [
    # Characters
    (frozenset({"resonators", "playable characters"}), PageTypeEnum.CHARACTER, 0.95),
    (frozenset({"5-star resonators", "4-star resonators"}), PageTypeEnum.CHARACTER, 0.95),
    (frozenset({"characters"}), PageTypeEnum.CHARACTER, 0.85),

    # Weapons
    (frozenset({"broadblades", "swords", "pistols", "rectifiers", "gauntlets"}), PageTypeEnum.WEAPON, 0.95),
    (frozenset({"weapons"}), PageTypeEnum.WEAPON, 0.90),
    (frozenset({"5-star weapons", "4-star weapons", "3-star weapons"}), PageTypeEnum.WEAPON, 0.95),

    # Echoes
    (frozenset({"echoes"}), PageTypeEnum.ECHO, 0.90),
    (frozenset({"echo", "sonata effects"}), PageTypeEnum.ECHO, 0.85),

    # Bosses
    (frozenset({"bosses", "weekly bosses", "overworld bosses"}), PageTypeEnum.BOSS, 0.90),
    (frozenset({"enemies"}), PageTypeEnum.BOSS, 0.70),

    # Quests
    (frozenset({"archon quests", "companion quests"}), PageTypeEnum.QUEST, 0.95),
    (frozenset({"world quests", "side quests", "quests"}), PageTypeEnum.QUEST, 0.90),

    # Items
    (frozenset({"materials", "consumables", "resources"}), PageTypeEnum.ITEM, 0.90),
    (frozenset({"items"}), PageTypeEnum.ITEM, 0.85),

    # Regions
    (frozenset({"regions", "sub-regions", "areas"}), PageTypeEnum.REGION, 0.90),
    (frozenset({"lahai-roi", "jinzhou", "rinascita", "new federation", "black shores"}), PageTypeEnum.REGION, 0.80),

    # Factions
    (frozenset({"factions", "organizations"}), PageTypeEnum.FACTION, 0.90),

    # NPCs
    (frozenset({"npcs", "non-playable characters"}), PageTypeEnum.NPC, 0.90),

    # Mechanics
    (frozenset({"game mechanics", "combat mechanics", "systems"}), PageTypeEnum.MECHANIC, 0.90),

    # Tutorials
    (frozenset({"tutorials", "guides"}), PageTypeEnum.TUTORIAL, 0.85),

    # Timeline
    (frozenset({"timeline", "lore timeline"}), PageTypeEnum.TIMELINE, 0.90),

    # Dialogue
    (frozenset({"dialogue", "voice lines"}), PageTypeEnum.DIALOGUE, 0.85),

    # Meta/Navigation
    (frozenset({"navigation templates", "disambiguation"}), PageTypeEnum.META_NAVIGATION, 0.90),
]


# ─────────────────────────────────────────────────────────────
# Infobox name → PageType mapping
# ─────────────────────────────────────────────────────────────

_INFOBOX_RULES: dict[str, Tuple[PageTypeEnum, float]] = {
    "character infobox": (PageTypeEnum.CHARACTER, 0.95),
    "character": (PageTypeEnum.CHARACTER, 0.90),
    "weapon infobox": (PageTypeEnum.WEAPON, 0.95),
    "weapon": (PageTypeEnum.WEAPON, 0.90),
    "echo infobox": (PageTypeEnum.ECHO, 0.95),
    "echo": (PageTypeEnum.ECHO, 0.90),
    "boss infobox": (PageTypeEnum.BOSS, 0.95),
    "enemy infobox": (PageTypeEnum.BOSS, 0.90),
    "quest infobox": (PageTypeEnum.QUEST, 0.90),
    "item infobox": (PageTypeEnum.ITEM, 0.90),
    "npc infobox": (PageTypeEnum.NPC, 0.90),
    "region infobox": (PageTypeEnum.REGION, 0.90),
    "faction infobox": (PageTypeEnum.FACTION, 0.90),
}


# ─────────────────────────────────────────────────────────────
# Title-based heuristic patterns
# ─────────────────────────────────────────────────────────────

_TITLE_PATTERNS: List[Tuple[re.Pattern[str], PageTypeEnum, float]] = [
    # Character subpages (e.g. Aalto/Backstory, Aalto/Forte Examination Report)
    (re.compile(r"^.+/(?:Backstory|Forte Examination Report|Voice Lines|Trivia|Gallery|Stats|Ascension)$", re.IGNORECASE), PageTypeEnum.CHARACTER, 0.90),

    # Quests often have distinctive naming
    (re.compile(r"^(?:Chapter|Act|Part)\s+\d+", re.IGNORECASE), PageTypeEnum.QUEST, 0.75),

    # Voice lines pages
    (re.compile(r"voice[\s_-]?lines?$", re.IGNORECASE), PageTypeEnum.DIALOGUE, 0.80),

    # Disambiguation pages
    (re.compile(r"\(disambiguation\)$", re.IGNORECASE), PageTypeEnum.META_NAVIGATION, 0.95),

    # List pages
    (re.compile(r"^list of\s", re.IGNORECASE), PageTypeEnum.META_NAVIGATION, 0.70),

    # Category pages
    (re.compile(r"^category:", re.IGNORECASE), PageTypeEnum.META_NAVIGATION, 0.95),
]


# ─────────────────────────────────────────────────────────────
# Content heuristic keywords
# ─────────────────────────────────────────────────────────────

_CONTENT_HEURISTIC_SECTIONS: dict[str, Tuple[PageTypeEnum, float]] = {
    "resonance skill": (PageTypeEnum.CHARACTER, 0.65),
    "forte circuit": (PageTypeEnum.CHARACTER, 0.70),
    "resonance chain": (PageTypeEnum.CHARACTER, 0.70),
    "resonance liberation": (PageTypeEnum.CHARACTER, 0.65),
    "ascension materials": (PageTypeEnum.WEAPON, 0.60),
    "weapon passive": (PageTypeEnum.WEAPON, 0.65),
    "sonata effect": (PageTypeEnum.ECHO, 0.65),
    "attack patterns": (PageTypeEnum.BOSS, 0.60),
    "quest objectives": (PageTypeEnum.QUEST, 0.65),
    "quest steps": (PageTypeEnum.QUEST, 0.60),
    "dialogue": (PageTypeEnum.QUEST, 0.50),
    "departments": (PageTypeEnum.FACTION, 0.55),
    "members": (PageTypeEnum.FACTION, 0.45),
}


# ─────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────


def classify_page_type(
    categories: Optional[List[str]] = None,
    infobox_name: Optional[str] = None,
    title: Optional[str] = None,
    section_titles: Optional[List[str]] = None,
    *,
    page_id: Optional[int] = None,
) -> ClassificationResult:
    """
    Classify a wiki page into a PageTypeEnum with confidence scoring.

    Applies classification sources in priority order (§5.1):
        1. Category-based (highest priority, 0.80–0.95 confidence)
        2. Infobox-based (0.90–0.95 confidence)
        3. Title heuristics (0.70–0.95 confidence)
        4. Content heuristics via section titles (0.45–0.70 confidence)
        5. Falls back to GENERIC with low confidence

    Early detection for skip pages:
        - Redirects detected upstream (in RawPageMeta.is_redirect)
        - Disambiguation pages detected via title pattern
        - Category/navigation pages detected via title prefix

    Args:
        categories: Wiki categories (e.g., ["Resonators", "5-Star"]).
        infobox_name: Infobox template name (e.g., "Character Infobox").
        title: Page title.
        section_titles: List of section heading titles in the page
            (for content-based heuristics).
        page_id: Optional page ID for structured log context.

    Returns:
        ClassificationResult with page_type, confidence, and provenance.

    Example::

        result = classify_page_type(
            categories=["Resonators", "5-Star Resonators"],
            infobox_name="Character Infobox",
            title="Kuchiba Chisa",
        )
        # result.page_type == PageTypeEnum.CHARACTER
        # result.confidence == 0.95
        # result.source == "category"
    """
    log_ctx = {"page_id": page_id} if page_id else {}
    categories = categories or []
    section_titles = section_titles or []

    # Normalize inputs for matching
    categories_lower = {c.lower().strip() for c in categories}
    infobox_lower = (infobox_name or "").lower().strip()
    title_str = (title or "").strip()

    # ── Source 1: Category-based classification ──
    for rule_keywords, page_type, confidence in _CATEGORY_RULES:
        if rule_keywords & categories_lower:
            matched = rule_keywords & categories_lower
            is_skip = page_type in (PageTypeEnum.QUEST, PageTypeEnum.DIALOGUE)
            result = ClassificationResult(
                page_type=page_type,
                confidence=confidence,
                source="category",
                matched_rule=f"categories matched: {sorted(matched)}",
                is_skip=is_skip,
                skip_reason="Quests & Dialogue pages skipped per user instruction" if is_skip else None,
            )
            logger.debug("page_classified", result=result.model_dump(), **log_ctx)
            return result

    # ── Source 2: Infobox-based classification ──
    if infobox_lower and infobox_lower in _INFOBOX_RULES:
        page_type, confidence = _INFOBOX_RULES[infobox_lower]
        result = ClassificationResult(
            page_type=page_type,
            confidence=confidence,
            source="infobox",
            matched_rule=f"infobox template: {infobox_name}",
        )
        logger.debug("page_classified", result=result.model_dump(), **log_ctx)
        return result

    # Partial infobox match (e.g., "Weapon Stats Infobox" contains "weapon")
    if infobox_lower:
        for pattern, (page_type, confidence) in _INFOBOX_RULES.items():
            if pattern in infobox_lower:
                result = ClassificationResult(
                    page_type=page_type,
                    confidence=confidence * 0.9,  # Slightly lower for partial match
                    source="infobox",
                    matched_rule=f"infobox partial match: '{pattern}' in '{infobox_name}'",
                )
                logger.debug("page_classified", result=result.model_dump(), **log_ctx)
                return result

    # ── Source 3: Title heuristics ──
    if title_str:
        for pattern, page_type, confidence in _TITLE_PATTERNS:
            if pattern.search(title_str):
                is_skip = page_type == PageTypeEnum.META_NAVIGATION
                result = ClassificationResult(
                    page_type=page_type,
                    confidence=confidence,
                    source="title",
                    matched_rule=f"title pattern: {pattern.pattern}",
                    is_skip=is_skip,
                    skip_reason="Navigation/disambiguation page" if is_skip else None,
                )
                logger.debug("page_classified", result=result.model_dump(), **log_ctx)
                return result

    # ── Source 4: Content heuristics (section title analysis) ──
    if section_titles:
        sections_lower = {s.lower().strip() for s in section_titles}
        best_match: Optional[Tuple[PageTypeEnum, float, str]] = None

        for heuristic_section, (page_type, confidence) in _CONTENT_HEURISTIC_SECTIONS.items():
            for section in sections_lower:
                if heuristic_section in section:
                    if best_match is None or confidence > best_match[1]:
                        best_match = (page_type, confidence, heuristic_section)

        if best_match:
            result = ClassificationResult(
                page_type=best_match[0],
                confidence=best_match[1],
                source="heuristic",
                matched_rule=f"section heuristic: '{best_match[2]}' found",
            )
            logger.debug("page_classified", result=result.model_dump(), **log_ctx)
            return result

    # ── Fallback: GENERIC with low confidence ──
    result = ClassificationResult(
        page_type=PageTypeEnum.GENERIC,
        confidence=0.3,
        source="fallback",
        matched_rule="no rule matched, defaulting to GENERIC",
    )
    logger.debug("page_classified_fallback", result=result.model_dump(), **log_ctx)
    return result
