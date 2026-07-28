"""
Canonical Page Schema — The "Golden" Intermediate Dataset (§4A of Architecture Doc).

This is the single most important schema in the entire pipeline. The Canonical
Dataset (``data/canonical/canonical.jsonl``) sits at the DECOUPLING BOUNDARY
between expensive upstream processing and cheap downstream experimentation.

A CanonicalPage is:
    1. Fully parsed:     No wiki markup remains
    2. Fully normalized: Clean, consistent text
    3. Fully enriched:   All document-level metadata attached
    4. Fully resolved:   Entities, aliases, relationships extracted
    5. Chunking-agnostic: No chunking decisions baked in
    6. Embedding-agnostic: No embedding model assumptions

This enables re-chunking / re-embedding without re-crawling or re-parsing.
"""

from __future__ import annotations
import enum
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


# ─────────────────────────────────────────────────────────────
# Enums
# ─────────────────────────────────────────────────────────────


class PageTypeEnum(str, enum.Enum):
    """
    Game wiki page type taxonomy.

    Determines which parser strategy and chunking approach are applied.
    Derived from categories, infobox templates, and heuristics (§5.1).
    """

    CHARACTER = "CHARACTER"
    WEAPON = "WEAPON"
    ECHO = "ECHO"
    BOSS = "BOSS"
    QUEST = "QUEST"
    ITEM = "ITEM"
    REGION = "REGION"
    FACTION = "FACTION"
    NPC = "NPC"
    MECHANIC = "MECHANIC"
    TUTORIAL = "TUTORIAL"
    TIMELINE = "TIMELINE"
    DIALOGUE = "DIALOGUE"
    META_NAVIGATION = "META_NAVIGATION"
    GENERIC = "GENERIC"


class ContentTypeEnum(str, enum.Enum):
    """
    Section-level content type classification.

    Drives content-type-aware chunking strategy selection (§8.2):
        PROSE           → Semantic paragraph chunking
        TABLE           → Row-group chunking with header injection
        DIALOGUE        → Scene-based chunking preserving speaker turns
        LIST            → List-group chunking
        STAT_BLOCK      → Atomic chunking (never split)
        SKILL_DESC      → Atomic chunking (never split)
        FORMULA         → Atomic chunking (never split)
        ATOMIC          → General atomic chunking (never split)
        HEADING_ONLY    → Section header with no body content
        PROSE_WITH_LIST → Mixed prose and structured list
    """

    PROSE = "PROSE"
    TABLE = "TABLE"
    DIALOGUE = "DIALOGUE"
    LIST = "LIST"
    STAT_BLOCK = "STAT_BLOCK"
    SKILL_DESC = "SKILL_DESC"
    FORMULA = "FORMULA"
    ATOMIC = "ATOMIC"
    HEADING_ONLY = "HEADING_ONLY"
    PROSE_WITH_LIST = "PROSE_WITH_LIST"


class IssueSeverityEnum(str, enum.Enum):
    """Severity level for quality issues detected during parsing."""

    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


# ─────────────────────────────────────────────────────────────
# Sub-models: Provenance & Sections
# ─────────────────────────────────────────────────────────────


class ProvenanceRecord(BaseModel):
    """
    Source attribution for a section's content.

    Tracks where each piece of content originated, enabling bilingual
    merge (EN wiki crawl + VI curated lore) with explicit auditable provenance.
    See §4A.5 for the bilingual data problem.

    Priority values:
        - ``primary``:     Main source of truth (typically EN wiki crawl)
        - ``supplement``:  Additional context (typically VI curated)
        - ``override``:    Replaces primary content (manual correction)
    """

    model_config = ConfigDict(extra="ignore")

    origin: str = Field(
        ...,
        description=(
            "Data source identifier: 'wiki_crawl', 'curated', 'llm_enriched', 'manual'."
        ),
    )
    language: str = Field(
        default="en",
        description="ISO-639-1 language code of the content.",
    )
    revision_id: Optional[int] = Field(
        default=None,
        description="Wiki revision ID if sourced from crawl.",
    )
    author: Optional[str] = Field(
        default=None,
        description="Author attribution for curated/manual content.",
    )
    priority: str = Field(
        default="primary",
        description="Merge priority: 'primary', 'supplement', or 'override'.",
    )
    content: Optional[str] = Field(
        default=None,
        description=(
            "Source-specific content snapshot. Preserved so the merge "
            "strategy is auditable even after content is merged."
        ),
    )


class CanonicalSection(BaseModel):
    """
    A single section within a Canonical Page.

    Sections form the fundamental content unit between parsing and chunking.
    Each section is content-type-tagged to drive downstream chunking strategy.

    The ``structured_data`` field holds parsed tabular/structured content
    (e.g., staff tables, stat blocks) as a list of row dicts. This keeps
    structured information queryable without re-parsing.
    """

    model_config = ConfigDict(extra="ignore")

    section_id: str = Field(
        ...,
        description=(
            "Deterministic section ID: '{page_id}-H{level}-{index}' "
            "(e.g., '54321-H2-02-H3-01')."
        ),
    )
    title: str = Field(
        ...,
        description="Section heading text, stripped of markup.",
    )
    level: int = Field(
        ...,
        ge=1,
        le=6,
        description="Heading level (1=H1/lead, 2=H2, 3=H3, etc.).",
    )
    content: str = Field(
        default="",
        description=(
            "Normalized plain text / markdown content of the section. "
            "Empty string for HEADING_ONLY sections."
        ),
    )
    content_type: ContentTypeEnum = Field(
        default=ContentTypeEnum.PROSE,
        description="Content classification driving chunking strategy.",
    )
    structured_data: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description=(
            "Parsed structured content (table rows as dicts, skill params, etc.). "
            "Only populated for TABLE, STAT_BLOCK, SKILL_DESC content types."
        ),
    )
    entities_in_section: List[str] = Field(
        default_factory=list,
        description="Canonical entity names mentioned in this section.",
    )
    sources: List[ProvenanceRecord] = Field(
        default_factory=list,
        description="Provenance chain for bilingual content merge tracking.",
    )
    subsections: Optional[List[CanonicalSection]] = Field(
        default=None,
        description=(
            "Nested sub-sections (e.g., H3 under H2). Recursive structure "
            "mirrors the wiki heading hierarchy."
        ),
    )


# ─────────────────────────────────────────────────────────────
# Sub-models: Identity, Metadata, Entities, Quality
# ─────────────────────────────────────────────────────────────


class CanonicalIdentity(BaseModel):
    """
    Core identification fields for a canonical page.

    These fields uniquely identify the page and determine downstream routing.
    """

    model_config = ConfigDict(extra="ignore")

    page_id: int = Field(
        ...,
        description="MediaWiki page ID — stable numeric identifier.",
    )
    title: str = Field(
        ...,
        description="Page title as returned by the API.",
    )
    canonical_slug: str = Field(
        ...,
        description=(
            "URL-safe slug derived from title "
            "(e.g., 'startorch_academy'). Used as filesystem key."
        ),
    )
    page_type: PageTypeEnum = Field(
        default=PageTypeEnum.GENERIC,
        description="Classified page type driving parser/chunker selection.",
    )
    page_type_confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Classification confidence score (0.0–1.0).",
    )


class DocumentMetadata(BaseModel):
    """
    Document-level metadata extracted ONCE per page (§6.0 Metadata-First).

    All chunks from this page inherit these fields, eliminating redundant
    per-chunk extraction and ensuring cross-chunk consistency.
    """

    model_config = ConfigDict(extra="ignore")

    canonical_name: Optional[str] = Field(
        default=None,
        description="Primary canonical entity name (e.g., 'Startorch Academy').",
    )
    entity_type: Optional[str] = Field(
        default=None,
        description="Primary entity classification: CHARACTER, WEAPON, ORGANIZATION, etc.",
    )
    region: Optional[str] = Field(
        default=None,
        description="Game region association (e.g., 'Lahai-Roi', 'Jinzhou').",
    )
    faction: Optional[str] = Field(
        default=None,
        description="Faction association (e.g., 'Huanglong', 'Spacetrek Collective').",
    )
    element: Optional[str] = Field(
        default=None,
        description="Elemental attribute for characters/weapons (e.g., 'Aero', 'Spectro').",
    )
    rarity: Optional[int] = Field(
        default=None,
        ge=1,
        le=5,
        description="Star rarity (1–5) for characters, weapons, echoes.",
    )
    weapon_type: Optional[str] = Field(
        default=None,
        description="Weapon category (e.g., 'Broadblade', 'Rectifier').",
    )
    game_version: Optional[str] = Field(
        default=None,
        description="Game version this content was introduced or last updated (e.g., '2.8').",
    )
    categories: List[str] = Field(
        default_factory=list,
        description="Wiki categories associated with the page.",
    )


class ExtractedEntity(BaseModel):
    """
    An entity mention extracted from the page content or infobox.

    Entities are resolved at document level and propagated to chunks
    during the metadata inheritance step.
    """

    model_config = ConfigDict(extra="ignore")

    name: str = Field(
        ...,
        description="Entity surface form as it appears in text.",
    )
    type: str = Field(
        ...,
        description="Entity type: CHARACTER, WEAPON, REGION, ORGANIZATION, etc.",
    )
    is_primary: bool = Field(
        default=False,
        description="Whether this is the page's primary subject entity.",
    )
    role: Optional[str] = Field(
        default=None,
        description="Contextual role (e.g., 'President', 'Student', 'Professor').",
    )
    canonical_name: Optional[str] = Field(
        default=None,
        description="Resolved canonical name from the alias registry.",
    )
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Extraction confidence (1.0 for dictionary-matched).",
    )
    source: str = Field(
        default="parser",
        description="Extraction method: 'parser', 'dictionary', 'wiki_link', 'llm'.",
    )


class EntityRelationship(BaseModel):
    """
    A directed relationship between two entities on the page.

    Used for knowledge graph construction and cross-page linking.
    """

    model_config = ConfigDict(extra="ignore")

    source: str = Field(
        ...,
        description="Source entity canonical name.",
    )
    relation: str = Field(
        ...,
        description="Relationship type (e.g., 'LOCATED_IN', 'STUDENT_AT', 'LEADS').",
    )
    target: str = Field(
        ...,
        description="Target entity canonical name.",
    )
    evidence_text: Optional[str] = Field(
        default=None,
        description="Text snippet supporting this relationship extraction.",
    )


class QualityIssue(BaseModel):
    """
    A single quality issue detected during parsing/normalization.

    Collected into QualityReport for per-page quality scoring.
    """

    model_config = ConfigDict(extra="ignore")

    type: str = Field(
        ...,
        description=(
            "Issue classification: MALFORMED_TABLE, BROKEN_HEADING, "
            "EMPTY_SECTION, IMAGE_REF_IN_LIST, etc."
        ),
    )
    location: str = Field(
        default="",
        description="Human-readable location descriptor (e.g., 'line 15-55', '## Descriptions').",
    )
    severity: IssueSeverityEnum = Field(
        default=IssueSeverityEnum.MEDIUM,
        description="Impact severity for quality scoring.",
    )
    count: Optional[int] = Field(
        default=None,
        description="Occurrence count for repeating issues (e.g., 12 image refs).",
    )
    message: Optional[str] = Field(
        default=None,
        description="Detailed human-readable description of the issue.",
    )


class QualityReport(BaseModel):
    """
    Aggregate quality assessment for a parsed page.

    The ``parser_confidence`` score determines whether LLM fallback
    is triggered (threshold typically 0.7, configurable).

    Quality score interpretation:
        - > 0.8:   Auto-approve
        - 0.5–0.8: Approve with warnings
        - < 0.5:   Quarantine for review
    """

    model_config = ConfigDict(extra="ignore")

    parser_confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Overall parse confidence score (0.0–1.0).",
    )
    issues: List[QualityIssue] = Field(
        default_factory=list,
        description="List of detected quality issues.",
    )
    tables_parsed: int = Field(
        default=0,
        ge=0,
        description="Number of tables successfully parsed.",
    )
    tables_failed: int = Field(
        default=0,
        ge=0,
        description="Number of tables that failed to parse.",
    )
    templates_stripped: int = Field(
        default=0,
        ge=0,
        description="Number of wiki templates removed during normalization.",
    )
    boilerplate_removed: List[str] = Field(
        default_factory=list,
        description="Section titles of removed boilerplate (e.g., 'Other Languages').",
    )


# ─────────────────────────────────────────────────────────────
# Sub-model: Pipeline Metadata
# ─────────────────────────────────────────────────────────────


class CanonicalMeta(BaseModel):
    """
    Pipeline processing metadata for the canonical record.

    Tracks schema version, creation time, and upstream source references
    for reproducibility and debugging.
    """

    model_config = ConfigDict(extra="ignore")

    canonical_version: str = Field(
        default="1.0.0",
        description="Semantic version of the canonical schema.",
    )
    pipeline_version: str = Field(
        default="2.1.0",
        description="Version of the ingestion pipeline that produced this record.",
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp when this canonical record was created.",
    )
    source_revision_id: Optional[int] = Field(
        default=None,
        description="MediaWiki revision ID of the source wikitext.",
    )
    raw_content_hash: Optional[str] = Field(
        default=None,
        description="SHA-256 hash of the raw wikitext for change detection (e.g., 'sha256:abc123...').",
    )
    parser_used: str = Field(
        default="hybrid",
        description="Parser strategy applied: 'parser_only', 'llm_only', 'hybrid'.",
    )
    llm_invoked: bool = Field(
        default=False,
        description="Whether LLM was invoked for any enrichment during processing.",
    )
    processing_time_ms: Optional[int] = Field(
        default=None,
        ge=0,
        description="Total processing time in milliseconds for this page.",
    )


# ─────────────────────────────────────────────────────────────
# Top-level: CanonicalPage
# ─────────────────────────────────────────────────────────────


class CanonicalPage(BaseModel):
    """
    The Canonical Dataset record — self-contained "golden" representation
    of a single wiki page.

    This is the **single most critical data structure** in the pipeline.
    It answers: "What does our system know about [page title]?" without
    joining across files. Every field needed for downstream chunking,
    embedding, and retrieval is present in this one record.

    Storage: One JSON line per page in ``data/canonical/canonical.jsonl``.

    Architecture reference: §4A of the Ingestion Architecture Document.

    Example usage::

        page = CanonicalPage(
            _meta=CanonicalMeta(source_revision_id=789012),
            identity=CanonicalIdentity(
                page_id=54321,
                title="Startorch Academy",
                canonical_slug="startorch_academy",
                page_type=PageTypeEnum.GENERIC,
                page_type_confidence=0.95,
            ),
            document_metadata=DocumentMetadata(
                canonical_name="Startorch Academy",
                region="Lahai-Roi",
            ),
            sections=[...],
        )
        json_line = page.model_dump_json()
    """

    model_config = ConfigDict(
        extra="ignore",
        populate_by_name=True,
    )

    # Pipeline metadata
    meta: CanonicalMeta = Field(
        default_factory=CanonicalMeta,
        alias="_meta",
        description="Pipeline processing metadata and schema version.",
    )

    # Page identity
    identity: CanonicalIdentity = Field(
        ...,
        description="Core identification: page_id, title, slug, type.",
    )

    # Document-level metadata (inherited by all chunks)
    document_metadata: DocumentMetadata = Field(
        default_factory=DocumentMetadata,
        description=(
            "Document-level metadata extracted ONCE per page. "
            "All chunks inherit these fields."
        ),
    )

    # Entities & relationships
    entities: List[ExtractedEntity] = Field(
        default_factory=list,
        description="All entities extracted from this page.",
    )
    relationships: List[EntityRelationship] = Field(
        default_factory=list,
        description="Entity-to-entity relationships discovered on this page.",
    )
    cross_references: List[str] = Field(
        default_factory=list,
        description="Page titles linked from this page (internal wiki links).",
    )

    # Infobox data
    infobox: Dict[str, Any] = Field(
        default_factory=dict,
        description="Structured key-value pairs from the page's infobox template.",
    )

    # Content sections (the core document body)
    sections: List[CanonicalSection] = Field(
        default_factory=list,
        description=(
            "Ordered list of document sections. Each section is content-type-tagged "
            "and may contain nested subsections."
        ),
    )

    # Quality assessment
    quality: QualityReport = Field(
        default_factory=QualityReport,
        description="Aggregate quality assessment from parsing/normalization.",
    )
