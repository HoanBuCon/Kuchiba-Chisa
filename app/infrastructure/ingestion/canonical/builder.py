"""
Canonical Page Builder — Assembles raw wikitext + curated lore into CanonicalPage.

Implements Stage 5 (Metadata & Entity Extraction) & Stage 5A (Canonicalization)
from §4A & §10 of the Ingestion Architecture Document v1.1.

Pipeline position:
    RawPage (EN Crawl) + Optional Curated Lore (VI)
                        ↓
            Canonical Layer Builder
                        ↓
      CanonicalPage (Golden Dataset Record)

Key Responsibilities:
    1. Extract infobox and tables using Upstream Parsers (§3).
    2. Sanitize wikitext, convert to markdown, and strip boilerplate.
    3. Classify page type and compute confidence score.
    4. Parse Markdown into hierarchical section tree (CanonicalSection).
    5. Detect content type per section (PROSE, TABLE, DIALOGUE, LIST, etc.).
    6. Extract document-level metadata, entities, and cross-references.
    7. Track bilingual provenance (EN primary + VI curated supplement).
    8. Generate aggregate QualityReport and return self-contained CanonicalPage.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple, Set

import structlog

from app.infrastructure.ingestion.models.canonical_page import (
    CanonicalIdentity,
    CanonicalMeta,
    CanonicalPage,
    CanonicalSection,
    ContentTypeEnum,
    DocumentMetadata,
    EntityRelationship,
    ExtractedEntity,
    IssueSeverityEnum,
    PageTypeEnum,
    ProvenanceRecord,
    QualityIssue,
    QualityReport,
)
from app.infrastructure.ingestion.models.raw_page import RawPage
from app.infrastructure.ingestion.parsers.classifier import classify_page_type
from app.infrastructure.ingestion.parsers.infobox_parser import (
    extract_infobox,
    extract_templates,
)
from app.infrastructure.ingestion.parsers.sanitizer import (
    clean_categories,
    convert_wikitext_to_markdown,
    sanitize_header_title,
    sanitize_wikitext,
    strip_boilerplate_sections,
)
from app.infrastructure.ingestion.parsers.table_parser import extract_all_tables

logger = structlog.get_logger(__name__)

# Regex pattern for dialogue line: Speaker: "Quote" or Speaker: Quote
_RE_DIALOGUE_LINE = re.compile(
    r"^(?:[A-Z][a-zA-Z0-9_\s\.\-]{1,25}):\s*[\"“'].+[\"”']$",
    re.MULTILINE,
)

# Regex pattern for internal wiki links [[Link]] or [[Link|Text]]
_RE_WIKI_LINK = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")

# Regex pattern for markdown headings
_RE_HEADING = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)


def _derive_slug(title: str) -> str:
    """Derive URL-safe canonical slug from title."""
    slug = title.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s-]+", "_", slug)
    return slug or "untitled_page"


def _detect_content_type(
    text: str,
    has_table_data: bool,
) -> ContentTypeEnum:
    """
    Detect section-level content type.

    Drives downstream chunking strategy (§8.2).
    """
    if has_table_data:
        return ContentTypeEnum.TABLE

    if not text.strip():
        return ContentTypeEnum.HEADING_ONLY

    lines = [line.strip() for line in text.split("\n") if line.strip()]
    if not lines:
        return ContentTypeEnum.HEADING_ONLY

    # Dialogue check: 2+ speaker lines
    dialogue_matches = _RE_DIALOGUE_LINE.findall(text)
    if len(dialogue_matches) >= 2:
        return ContentTypeEnum.DIALOGUE

    # List check: > 50% of non-empty lines start with bullet/number
    list_lines = [
        l for l in lines if l.startswith(("- ", "* ", "1. ", "2. ", "3. "))
    ]
    if len(lines) >= 3 and len(list_lines) / len(lines) >= 0.5:
        return ContentTypeEnum.LIST

    if len(list_lines) > 0 and len(lines) > len(list_lines):
        return ContentTypeEnum.PROSE_WITH_LIST

    return ContentTypeEnum.PROSE


_ENTITY_PREFIX_STOPWORDS = frozenset({
    "when", "whenever", "under", "through", "even", "dear", "the", "a", "an",
    "on", "in", "at", "from", "to", "with", "by", "for", "about", "after",
    "before", "during", "while", "until", "since", "despite", "between",
})

_ENTITY_BLACKLIST = frozenset({
    "dear guest", "free service", "bad deal", "overview", "description",
    "trivia", "lead", "main", "page", "section", "even common echoes",
    "through leviathan", "each threnodian", "other languages", "campus life",
    "fan clubs", "resonator nursing unit",
})


def clean_entity_name(entity: str) -> str:
    """Clean entity name by removing leading prepositions/conjunctions and blacklisted noise."""
    if not entity:
        return ""
    clean = entity.strip()
    words = clean.split()
    if words and words[0].lower() in _ENTITY_PREFIX_STOPWORDS and len(words) > 1:
        clean = " ".join(words[1:])

    if clean.lower() in _ENTITY_BLACKLIST or len(clean) < 2:
        return ""
    return clean


def _extract_entities_from_text(text: str) -> List[str]:
    """Extract potential entity names from wiki links, markdown links, or capitalized names."""
    entities: Set[str] = set()

    # Wiki links [[Link]]
    for match in _RE_WIKI_LINK.finditer(text):
        cleaned = clean_entity_name(match.group(1))
        if cleaned:
            entities.add(cleaned)

    # Capitalized entity phrases (2-4 words, e.g. "Spacetrek Collective", "Startorch Academy", "Lahai-Roi")
    cap_phrase_regex = re.compile(r"\b([A-Z][a-z]+(?:[ \t]+[A-Z][a-z]+){1,3})\b")
    for match in cap_phrase_regex.finditer(text):
        cleaned = clean_entity_name(match.group(1))
        if cleaned:
            entities.add(cleaned)

    return sorted(list(entities))


import yaml
from pathlib import Path

_TAXONOMY_PATH = Path("app/infrastructure/ingestion/config/taxonomy.yaml")
_TAXONOMY_CACHE: Optional[Dict[str, Any]] = None

def _load_taxonomy() -> Dict[str, Any]:
    global _TAXONOMY_CACHE
    if _TAXONOMY_CACHE is None:
        if _TAXONOMY_PATH.exists():
            with open(_TAXONOMY_PATH, "r", encoding="utf-8") as f:
                _TAXONOMY_CACHE = yaml.safe_load(f) or {}
        else:
            _TAXONOMY_CACHE = {}
    return _TAXONOMY_CACHE

def _fallback_metadata_from_categories(categories: List[str], doc_metadata: DocumentMetadata) -> None:
    """Infer missing metadata fields (element, weapon_type, region, faction) from Taxonomy-as-Code & Wiki Categories."""
    cats_str = " ".join(categories).lower()
    taxonomy = _load_taxonomy()

    # Element
    if not doc_metadata.element:
        for elem_item in taxonomy.get("elements", []):
            elem_name = elem_item["name"]
            aliases = elem_item.get("aliases", [])
            if any(alias in cats_str for alias in aliases):
                doc_metadata.element = elem_name
                break

    # Weapon Type
    if not doc_metadata.weapon_type:
        for wpn_item in taxonomy.get("weapon_types", []):
            wpn_name = wpn_item["name"]
            aliases = wpn_item.get("aliases", [])
            if any(alias in cats_str for alias in aliases):
                doc_metadata.weapon_type = wpn_name
                break

    # Region
    if not doc_metadata.region:
        for reg_item in taxonomy.get("regions", []):
            reg_name = reg_item["name"]
            aliases = reg_item.get("aliases", [])
            if any(alias in cats_str for alias in aliases):
                doc_metadata.region = reg_name
                break

    # Faction
    if not doc_metadata.faction:
        for fac_item in taxonomy.get("factions", []):
            fac_name = fac_item["name"]
            aliases = fac_item.get("aliases", [])
            if any(alias in cats_str for alias in aliases):
                doc_metadata.faction = fac_name
                break


def _split_markdown_into_sections(
    markdown_text: str,
    page_id: int,
    parsed_tables: List[List[Dict[str, Any]]],
    provenance_sources: List[ProvenanceRecord],
) -> Tuple[List[CanonicalSection], List[QualityIssue]]:
    """
    Split markdown AST text into CanonicalSection models (§5.1 & §6.0).

    Returns:
        Tuple of (list of sections, list of section-level quality issues).
    """
    sections: List[CanonicalSection] = []
    issues: List[QualityIssue] = []

    matches = list(_RE_HEADING.finditer(markdown_text))
    table_index = 0

    if not matches:
        # Lead section without explicit heading
        content_type = _detect_content_type(markdown_text, False)
        sec = CanonicalSection(
            section_id=f"{page_id}-H1-00",
            title="Lead",
            level=1,
            content=markdown_text.strip(),
            content_type=content_type,
            entities_in_section=_extract_entities_from_text(markdown_text),
            sources=provenance_sources,
        )
        return [sec], issues

    # Handle content before the first heading (Lead)
    lead_content = markdown_text[: matches[0].start()].strip()
    if lead_content:
        content_type = _detect_content_type(lead_content, False)
        sections.append(
            CanonicalSection(
                section_id=f"{page_id}-H1-00",
                title="Lead",
                level=1,
                content=lead_content,
                content_type=content_type,
                entities_in_section=_extract_entities_from_text(lead_content),
                sources=provenance_sources,
            )
        )

    # Process heading sections
    for i, match in enumerate(matches):
        level = len(match.group(1))
        title = sanitize_header_title(match.group(2).strip())

        start_idx = match.end()
        end_idx = matches[i + 1].start() if i + 1 < len(matches) else len(markdown_text)
        content = markdown_text[start_idx:end_idx].strip()

        # Section ID format: {page_id}-H{level}-{i:02d}
        sec_id = f"{page_id}-H{level}-{i:02d}"

        # Assign table structured data if section mentions tables or contains wiki table leftovers
        structured_data: Optional[List[Dict[str, Any]]] = None
        has_table_data = False

        if table_index < len(parsed_tables) and (
            "table" in title.lower()
            or "staff" in title.lower()
            or "students" in title.lower()
            or "members" in title.lower()
            or "{|" in content
        ):
            structured_data = parsed_tables[table_index]
            table_index += 1
            has_table_data = True

        content_type = _detect_content_type(content, has_table_data)

        if content_type == ContentTypeEnum.HEADING_ONLY and not has_table_data and not content:
            # Skip empty container headings (e.g., ## Archives, ## Character Stories)
            continue

        sec = CanonicalSection(
            section_id=sec_id,
            title=title,
            level=level,
            content=content,
            content_type=content_type,
            structured_data=structured_data,
            entities_in_section=_extract_entities_from_text(content),
            sources=provenance_sources,
        )
        sections.append(sec)

    return sections, issues


def _separate_bilingual_lore(
    raw_wikitext: str,
    curated_text: Optional[str],
    revision_id: int,
) -> Tuple[str, Optional[str], List[ProvenanceRecord]]:
    """
    Separate raw EN crawl text from curated VI lore text.

    Supports explicit `curated_text` argument OR combined files containing
    `[Data cũ]` / `[Data mới crawl...]` markers like `startorch_academy.md`.
    """
    sources: List[ProvenanceRecord] = [
        ProvenanceRecord(
            origin="wiki_crawl",
            language="en",
            revision_id=revision_id,
            priority="primary",
        )
    ]

    en_text = raw_wikitext
    vi_text = curated_text

    # Check for inline marker blocks if no separate curated_text provided
    if not vi_text and ("[Data cũ]" in raw_wikitext or "[Data mới" in raw_wikitext):
        parts = re.split(r"\[Data (?:cũ|mới[^\]]*)\]", raw_wikitext)
        cleaned_parts = [p.strip() for p in parts if p.strip()]

        if len(cleaned_parts) >= 2:
            # First part is old/curated VI data, second part is raw EN crawl
            vi_text = cleaned_parts[0]
            en_text = cleaned_parts[1]
        elif len(cleaned_parts) == 1:
            en_text = cleaned_parts[0]

    if vi_text:
        sources.append(
            ProvenanceRecord(
                origin="curated",
                language="vi",
                priority="supplement",
                content=vi_text.strip(),
            )
        )

    return en_text, vi_text, sources


from app.infrastructure.ingestion.canonical.entity_registry import (
    EntityRecord,
    EntityRegistry,
    RelationshipRecord,
)

logger = structlog.get_logger(__name__)


def build_canonical_page(
    raw_page: RawPage,
    *,
    curated_text: Optional[str] = None,
    registry: Optional[EntityRegistry] = None,
    pipeline_version: str = "2.1.0",
) -> CanonicalPage:
    """
    Build a CanonicalPage record from a RawPage.

    This is the core factory for Stage 5A (Canonicalization) & Stage 5 (Entity Extraction).

    Args:
        raw_page: Immutable raw page containing metadata and raw wikitext.
        curated_text: Optional Vietnamese curated lore text to merge.
        registry: Optional EntityRegistry instance for entity & relationship resolution.
        pipeline_version: Version of the ingestion pipeline.

    Returns:
        Fully populated CanonicalPage instance ready for canonical.jsonl streaming.
    """
    if registry is None:
        registry = EntityRegistry()
    meta = raw_page.meta
    page_id = meta.page_id
    title = meta.title
    revision_id = meta.revision_id

    logger.info("building_canonical_page", page_id=page_id, title=title)

    # 1. Separate EN crawl and VI curated content & build provenance
    en_wikitext, vi_text, provenance_sources = _separate_bilingual_lore(
        raw_page.wikitext, curated_text, revision_id
    )

    # 2. Extract Infobox & Tables BEFORE wikitext sanitization
    infobox_data, infobox_name = extract_infobox(en_wikitext, page_id=page_id)
    templates = extract_templates(en_wikitext, page_id=page_id)
    parsed_tables, tables_ok, tables_fail = extract_all_tables(en_wikitext, page_id=page_id)

    # 3. Sanitize wikitext
    sanitized = sanitize_wikitext(en_wikitext, page_id=page_id, page_title=title)

    # 4. Convert to Markdown & strip boilerplate
    markdown = convert_wikitext_to_markdown(sanitized)
    clean_markdown, removed_boilerplate = strip_boilerplate_sections(
        markdown, page_type=None
    )

    # 5. Extract section titles for classification heuristics
    temp_sections, _ = _split_markdown_into_sections(
        clean_markdown, page_id, parsed_tables, provenance_sources
    )
    section_titles = [s.title for s in temp_sections]

    # 6. Classify page type
    classification = classify_page_type(
        categories=meta.categories,
        infobox_name=infobox_name if infobox_name else None,
        title=title,
        section_titles=section_titles,
        page_id=page_id,
    )

    # 7. Final section build with quality issues
    sections, section_issues = _split_markdown_into_sections(
        clean_markdown, page_id, parsed_tables, provenance_sources
    )

    # 8. Document-Level Metadata Extraction (§6.0)
    clean_cats = clean_categories(meta.categories)

    # Extract Profile Header fields if infobox missing
    if not infobox_data.get("faction"):
        aff_match = re.search(r"(?:Affiliation|Faction):\s*([^,\.\n]+)", en_wikitext, re.IGNORECASE)
        if aff_match:
            infobox_data["faction"] = aff_match.group(1).strip()

    if not infobox_data.get("region"):
        orig_match = re.search(r"(?:Origin|Region):\s*([^,\.\n]+)", en_wikitext, re.IGNORECASE)
        if orig_match:
            infobox_data["region"] = orig_match.group(1).strip()

    doc_metadata = DocumentMetadata(
        canonical_name=infobox_data.get("name") or title,
        entity_type=infobox_data.get("type") or classification.page_type.value,
        region=infobox_data.get("region"),
        faction=infobox_data.get("faction"),
        element=infobox_data.get("element"),
        rarity=int(infobox_data["rarity"]) if infobox_data.get("rarity", "").isdigit() else None,
        weapon_type=infobox_data.get("weapon") or infobox_data.get("weapon_type"),
        categories=clean_cats,
    )

    # 1. Infer missing metadata from Categories
    _fallback_metadata_from_categories(clean_cats, doc_metadata)

    # 2. Subpage & Parent Metadata Synchronization
    parent_name = title.split("/")[0].strip() if "/" in title else title
    doc_metadata.canonical_name = parent_name
    parent_record = registry.get_entity(parent_name)

    if parent_record:
        # Inherit metadata from parent entity
        doc_metadata.canonical_name = parent_record.canonical_name
        doc_metadata.entity_type = parent_record.entity_type
        doc_metadata.faction = doc_metadata.faction or parent_record.attributes.get("faction")
        doc_metadata.element = doc_metadata.element or parent_record.attributes.get("element")
        if parent_record.attributes.get("rarity"):
            doc_metadata.rarity = doc_metadata.rarity or parent_record.attributes["rarity"]
        doc_metadata.weapon_type = doc_metadata.weapon_type or parent_record.attributes.get("weapon")
        doc_metadata.region = doc_metadata.region or parent_record.attributes.get("region")

        # Also update registry record attributes if doc_metadata has newly inferred fields
        for attr_key, attr_val in [
            ("faction", doc_metadata.faction),
            ("element", doc_metadata.element),
            ("rarity", doc_metadata.rarity),
            ("weapon", doc_metadata.weapon_type),
            ("region", doc_metadata.region),
        ]:
            if attr_val and not parent_record.attributes.get(attr_key):
                parent_record.attributes[attr_key] = attr_val
    else:
        # Register main entity in registry for subpages & parent pages to share
        registry.register_entity(
            EntityRecord(
                entity_id=_derive_slug(parent_name),
                canonical_name=parent_name,
                entity_type=classification.page_type.value,
                canonical_slug=_derive_slug(parent_name),
                page_id=page_id,
                attributes={
                    "faction": doc_metadata.faction,
                    "element": doc_metadata.element,
                    "rarity": doc_metadata.rarity,
                    "weapon": doc_metadata.weapon_type,
                    "region": doc_metadata.region,
                },
            )
        )

    # 9. Extract Entities & Relationships via EntityRegistry
    primary_name = registry.resolve_alias(doc_metadata.canonical_name or title) or (doc_metadata.canonical_name or title)
    entities: List[ExtractedEntity] = [
        ExtractedEntity(
            name=primary_name,
            type=classification.page_type.value,
            is_primary=True,
            confidence=1.0,
            source="parser",
        )
    ]

    relationships: List[EntityRelationship] = []

    if doc_metadata.region:
        reg_target = registry.resolve_alias(doc_metadata.region) or doc_metadata.region
        relationships.append(
            EntityRelationship(
                source=primary_name,
                relation="LOCATED_IN",
                target=reg_target,
            )
        )
        registry.register_relationship(primary_name, "LOCATED_IN", reg_target)

    if doc_metadata.faction:
        fac_target = registry.resolve_alias(doc_metadata.faction) or doc_metadata.faction
        relationships.append(
            EntityRelationship(
                source=primary_name,
                relation="AFFILIATED_WITH",
                target=fac_target,
            )
        )
        registry.register_relationship(primary_name, "AFFILIATED_WITH", fac_target)

    # Extract secondary entities from cross-references (wiki links / capitalized terms)
    cross_refs_raw = _extract_entities_from_text(raw_page.wikitext)
    cross_refs: List[str] = []
    seen_refs: Set[str] = set()

    for ref in cross_refs_raw:
        resolved = registry.resolve_alias(ref) or ref
        if resolved not in seen_refs and resolved != primary_name:
            seen_refs.add(resolved)
            cross_refs.append(resolved)

            # Check if resolved entity is in registry
            reg_rec = registry.get_entity(resolved)
            if reg_rec:
                entities.append(
                    ExtractedEntity(
                        name=reg_rec.canonical_name,
                        type=reg_rec.entity_type,
                        is_primary=False,
                        confidence=0.9,
                        source="entity_registry",
                    )
                )

    # 10. Quality Report
    all_issues = list(section_issues)
    if tables_fail > 0:
        all_issues.append(
            QualityIssue(
                type="MALFORMED_TABLE",
                location="Wiki tables",
                severity=IssueSeverityEnum.MEDIUM,
                count=tables_fail,
                message=f"{tables_fail} table(s) failed to parse completely.",
            )
        )

    quality_score = classification.confidence
    if tables_fail > 0:
        quality_score = max(0.1, quality_score - 0.1)

    quality = QualityReport(
        parser_confidence=quality_score,
        issues=all_issues,
        tables_parsed=tables_ok,
        tables_failed=tables_fail,
        templates_stripped=len(templates),
        boilerplate_removed=removed_boilerplate,
    )

    # Assemble final CanonicalPage
    canonical_page = CanonicalPage(
        _meta=CanonicalMeta(
            canonical_version="1.0.0",
            pipeline_version=pipeline_version,
            source_revision_id=revision_id,
            parser_used="hybrid",
            llm_invoked=False,
        ),
        identity=CanonicalIdentity(
            page_id=page_id,
            title=title,
            canonical_slug=_derive_slug(title),
            page_type=classification.page_type,
            page_type_confidence=classification.confidence,
        ),
        document_metadata=doc_metadata,
        entities=entities,
        relationships=relationships,
        cross_references=cross_refs,
        infobox=infobox_data,
        sections=sections,
        quality=quality,
    )

    logger.info(
        "canonical_page_built",
        page_id=page_id,
        sections=len(sections),
        tables=tables_ok,
        confidence=quality_score,
    )

    return canonical_page
