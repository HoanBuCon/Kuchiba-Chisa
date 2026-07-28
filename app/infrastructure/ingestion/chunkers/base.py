"""
Base Strategy Interface for Structure-Aware Chunkers (§8.2).

Defines the abstract interface BaseChunker and provides shared metadata inheritance
utilities so every chunk strategy correctly inherits document-level metadata from
its parent CanonicalPage (§6.0 Metadata-First Architecture).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

import structlog

from app.infrastructure.ingestion.models.canonical_page import CanonicalPage, CanonicalSection
from app.infrastructure.ingestion.models.chunk_model import Chunk, ChunkStrategyEnum

logger = structlog.get_logger(__name__)


class BaseChunker(ABC):
    """
    Abstract Strategy Interface for all content-type-aware chunkers.

    Subclasses implement ``chunk_section`` to transform a CanonicalSection into
    one or more retrieval-ready Chunk objects.
    """

    def __init__(
        self,
        target_token_size: int = 256,
        max_token_size: int = 512,
    ):
        """
        Initialize chunker configuration.

        Args:
            target_token_size: Ideal target token size for chunks (default 256).
            max_token_size: Maximum token ceiling before forcing a split (default 512).
        """
        self.target_token_size = target_token_size
        self.max_token_size = max_token_size

    @abstractmethod
    def chunk_section(
        self,
        page: CanonicalPage,
        section: CanonicalSection,
        heading_path: str,
    ) -> List[Chunk]:
        """
        Transform a CanonicalSection into a list of Chunk objects.

        Args:
            page: Parent CanonicalPage (provides document-level metadata for inheritance).
            section: Target section to chunk.
            heading_path: Full hierarchical heading path (e.g., 'Startorch Academy > Members > Staff').

        Returns:
            List of Chunk instances with inherited metadata and deterministic UUIDv5 IDs.
        """
        pass

    def _create_chunk(
        self,
        page: CanonicalPage,
        section: CanonicalSection,
        heading_path: str,
        chunk_index: int,
        text_content: str,
        strategy: ChunkStrategyEnum,
        entities_override: Optional[List[str]] = None,
    ) -> Chunk:
        """
        Helper method to construct a Chunk with complete document-level metadata inheritance.

        Ensures that document metadata (canonical_name, region, faction, element, etc.)
        is inherited ONCE from parent CanonicalPage without redundant per-chunk calls.
        Uses deterministic UUIDv5 for chunk_id generation.
        """
        doc_meta = page.document_metadata

        from app.infrastructure.ingestion.parsers.sanitizer import clean_entities, sanitize_header_title

        # Truncation & Bleed-Through Fix: Extract & filter entities strictly for THIS chunk text
        raw_entities = entities_override or section.entities_in_section
        entities = clean_entities(raw_entities, text_content=text_content)

        clean_heading_path = " > ".join(
            sanitize_header_title(p.strip()) for p in heading_path.split(" > ")
        )
        clean_section_title = sanitize_header_title(section.title) if section.title else None

        # Content-Type Aware Quality Score: High score (0.95) for clean prose text
        word_count = len(text_content.split())
        if word_count >= 30 and not text_content.startswith("{"):
            quality_score = 0.95
        elif word_count >= 15:
            quality_score = 0.85
        else:
            quality_score = 0.70

        return Chunk.from_text(
            page_id=page.identity.page_id,
            section_id=section.section_id,
            revision_id=page.meta.source_revision_id,
            heading_path=clean_heading_path,
            section_title=clean_section_title,
            section_depth=section.level,
            chunk_index=chunk_index,
            text_content=text_content,
            chunk_strategy=strategy,
            content_type=section.content_type.value,
            # Document metadata inheritance (§6.0)
            page_title=page.identity.title,
            page_type=page.identity.page_type.value,
            canonical_name=doc_meta.canonical_name,
            entity_type=doc_meta.entity_type,
            region=doc_meta.region,
            faction=doc_meta.faction,
            element=doc_meta.element,
            game_version=doc_meta.game_version,
            entities=entities,
            quality_score=quality_score,
        )
