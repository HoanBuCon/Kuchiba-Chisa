"""
Table Inliner Chunker — Converts tabular row dicts to natural prose chunks (§8.2).

Strategy:
    1. Reads structured table rows from CanonicalSection.structured_data (List[Dict[str, str]]).
    2. Converts each table row into a self-contained prose sentence:
       "Startorch Academy Staff: Name: Lucilla. Position: President of Startorch Academy, Professor."
    3. Groups rows up to target_token_size while guaranteeing NO single table row is split.
    4. Auto-extracts entity names from 'Name' or 'Character' columns in table rows.
    5. Sets ChunkStrategyEnum.TABLE_INLINE.
"""

from __future__ import annotations

from typing import Dict, List, Set

import structlog

from app.infrastructure.ingestion.chunkers.base import BaseChunker
from app.infrastructure.ingestion.models.canonical_page import CanonicalPage, CanonicalSection
from app.infrastructure.ingestion.models.chunk_model import Chunk, ChunkStrategyEnum, estimate_token_count

logger = structlog.get_logger(__name__)


class TableInlinerChunker(BaseChunker):
    """
    Chunker strategy for TABLE content types.

    Transforms structured tabular data into retrievable prose chunks.
    """

    def _inline_row(self, row: Dict[str, str], context_label: str) -> str:
        """
        Convert a single table row dict into a natural prose statement.

        Example::

            row = {"Name": "Lucilla", "Position": "President"}
            result = "Startorch Academy Staff row: Name: Lucilla. Position: President."
        """
        parts = [f"{k}: {v}" for k, v in row.items() if v]
        row_str = ". ".join(parts)
        if not row_str.endswith("."):
            row_str += "."

        return f"{context_label}: {row_str}"

    def chunk_section(
        self,
        page: CanonicalPage,
        section: CanonicalSection,
        heading_path: str,
    ) -> List[Chunk]:
        """
        Chunk a table section into table-inlined prose chunks.

        Args:
            page: Parent CanonicalPage.
            section: Section with structured table data.
            heading_path: Full heading path.

        Returns:
            List of Chunk objects with TABLE_INLINE strategy.
        """
        rows = section.structured_data or []

        # If no structured data available, fall back to prose line inlining
        if not rows:
            if not section.content.strip():
                return []
            # Create synthetic rows from text lines
            lines = [l.strip() for l in section.content.split("\n") if l.strip()]
            rows = [{"Content": l} for l in lines]

        chunks: List[Chunk] = []
        current_prose_rows: List[str] = []
        current_entities: Set[str] = set()
        current_tokens = 0
        chunk_idx = 0

        context_label = f"{page.identity.title} - {section.title}"

        for row in rows:
            prose_row = self._inline_row(row, context_label)
            row_tokens = estimate_token_count(prose_row)

            # Extract potential entity from "Name", "Character", "Item", etc.
            for key in ("Name", "Character", "Item", "Boss", "Weapon"):
                if key in row and row[key]:
                    current_entities.add(row[key])

            # Check max_token_size overflow
            if current_prose_rows and (current_tokens + row_tokens > self.max_token_size):
                chunk_text = "\n".join(current_prose_rows)
                entities = sorted(list(current_entities | set(section.entities_in_section)))

                chunks.append(
                    self._create_chunk(
                        page=page,
                        section=section,
                        heading_path=heading_path,
                        chunk_index=chunk_idx,
                        text_content=chunk_text,
                        strategy=ChunkStrategyEnum.TABLE_INLINE,
                        entities_override=entities,
                    )
                )

                chunk_idx += 1
                current_prose_rows = []
                current_entities = set()
                current_tokens = 0

            current_prose_rows.append(prose_row)
            current_tokens += row_tokens

            # Target token size reached
            if current_tokens >= self.target_token_size:
                chunk_text = "\n".join(current_prose_rows)
                entities = sorted(list(current_entities | set(section.entities_in_section)))

                chunks.append(
                    self._create_chunk(
                        page=page,
                        section=section,
                        heading_path=heading_path,
                        chunk_index=chunk_idx,
                        text_content=chunk_text,
                        strategy=ChunkStrategyEnum.TABLE_INLINE,
                        entities_override=entities,
                    )
                )

                chunk_idx += 1
                current_prose_rows = []
                current_entities = set()
                current_tokens = 0

        # Emit remaining rows
        if current_prose_rows:
            chunk_text = "\n".join(current_prose_rows)
            entities = sorted(list(current_entities | set(section.entities_in_section)))

            chunks.append(
                self._create_chunk(
                    page=page,
                    section=section,
                    heading_path=heading_path,
                    chunk_index=chunk_idx,
                    text_content=chunk_text,
                    strategy=ChunkStrategyEnum.TABLE_INLINE,
                    entities_override=entities,
                )
            )

        logger.debug(
            "table_section_inlined",
            heading_path=heading_path,
            rows_processed=len(rows),
            chunks_created=len(chunks),
        )

        return chunks
