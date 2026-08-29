"""
Generic Chunker — H2/H3 hierarchy & paragraph sliding window chunker (§8.2).

Strategy:
    1. Handles PROSE, LIST, and general content sections.
    2. Splits section text by double-newlines (paragraphs) or bullet lists.
    3. Merges consecutive paragraphs up to target_token_size (default 256 tokens).
    4. Guarantees chunks NEVER split mid-sentence.
    5. Implements sentence-level overlap (carries over last N sentences from previous chunk).
    6. Uses ChunkStrategyEnum.PARAGRAPH_MERGE or SLIDING_WINDOW.
"""

from __future__ import annotations

import re
from typing import List

import structlog

from app.infrastructure.ingestion.chunkers.base import BaseChunker
from app.infrastructure.ingestion.models.canonical_page import CanonicalPage, CanonicalSection
from app.infrastructure.ingestion.models.chunk_model import Chunk, ChunkStrategyEnum, estimate_token_count

logger = structlog.get_logger(__name__)

# Smart sentence boundary regex (preserves abbreviations like Lv. 90, v1.2, Dr. Honami, decimal 12.5%)
_RE_SENTENCE = re.compile(r"(?<!\b(?:Lv|v|No|Dr|Mr|Mrs|Ms|Prof|etc|approx|e\.g|i\.e|\d))\b(?<=[.!?])\s+(?=[A-ZÀ-Ỹ\"'‘“\[\(\d])")


class GenericChunker(BaseChunker):
    """
    Standard paragraph-merge and sliding-window chunker for prose content.
    """

    def __init__(
        self,
        target_token_size: int = 256,
        max_token_size: int = 512,
        overlap_sentences: int = 0,
    ):
        """
        Initialize GenericChunker.

        Args:
            target_token_size: Ideal target token budget per chunk.
            max_token_size: Max token limit per chunk.
            overlap_sentences: Number of tail sentences to overlap with the next chunk.
        """
        super().__init__(target_token_size=target_token_size, max_token_size=max_token_size)
        self.overlap_sentences = overlap_sentences

    def _split_sentences(self, text: str) -> List[str]:
        """Split text block into clean sentences."""
        raw_sentences = _RE_SENTENCE.split(text.strip())
        return [s.strip() for s in raw_sentences if s.strip()]

    def _split_paragraphs(self, text: str) -> List[str]:
        """Split text block into paragraphs by double-newline or bullet blocks."""
        paragraphs = text.split("\n\n")
        cleaned: List[str] = []

        for p in paragraphs:
            p_str = p.strip()
            if not p_str:
                continue

            # If paragraph itself is huge (> max_token_size), break into sentence blocks
            if estimate_token_count(p_str) > self.max_token_size:
                sentences = self._split_sentences(p_str)
                temp_block: List[str] = []
                temp_tokens = 0

                for s in sentences:
                    s_tokens = estimate_token_count(s)
                    if temp_block and (temp_tokens + s_tokens > self.target_token_size):
                        cleaned.append(" ".join(temp_block))
                        temp_block = []
                        temp_tokens = 0
                    temp_block.append(s)
                    temp_tokens += s_tokens

                if temp_block:
                    cleaned.append(" ".join(temp_block))
            else:
                cleaned.append(p_str)

        return cleaned

    def chunk_section(
        self,
        page: CanonicalPage,
        section: CanonicalSection,
        heading_path: str,
    ) -> List[Chunk]:
        """
        Chunk a prose/generic section using paragraph-merge and sentence overlap.

        Args:
            page: Parent CanonicalPage.
            section: Section to chunk.
            heading_path: Full heading path.

        Returns:
            List of Chunk objects with PARAGRAPH_MERGE or SLIDING_WINDOW strategy.
        """
        if not section.content.strip():
            return []

        paragraphs = self._split_paragraphs(section.content)
        if not paragraphs:
            return []

        chunks: List[Chunk] = []
        current_paragraphs: List[str] = []
        current_tokens = 0
        chunk_idx = 0
        overlap_prefix = ""

        for p in paragraphs:
            p_tokens = estimate_token_count(p)

            # Check if adding paragraph exceeds max_token_size
            if current_paragraphs and (current_tokens + p_tokens > self.max_token_size):
                body_text = "\n\n".join(current_paragraphs)
                full_chunk_text = f"{overlap_prefix}\n\n{body_text}" if overlap_prefix else body_text

                strategy = (
                    ChunkStrategyEnum.SLIDING_WINDOW
                    if overlap_prefix
                    else ChunkStrategyEnum.PARAGRAPH_MERGE
                )

                chunks.append(
                    self._create_chunk(
                        page=page,
                        section=section,
                        heading_path=heading_path,
                        chunk_index=chunk_idx,
                        text_content=full_chunk_text.strip(),
                        strategy=strategy,
                    )
                )

                # Compute sentence overlap for next chunk
                if self.overlap_sentences > 0:
                    last_text = current_paragraphs[-1]
                    sentences = self._split_sentences(last_text)
                    overlap_prefix = " ".join(sentences[-self.overlap_sentences :])
                else:
                    overlap_prefix = ""

                chunk_idx += 1
                current_paragraphs = []
                current_tokens = estimate_token_count(overlap_prefix) if overlap_prefix else 0

            current_paragraphs.append(p)
            current_tokens += p_tokens

            # Target token size reached
            if current_tokens >= self.target_token_size:
                body_text = "\n\n".join(current_paragraphs)
                full_chunk_text = f"{overlap_prefix}\n\n{body_text}" if overlap_prefix else body_text

                strategy = (
                    ChunkStrategyEnum.SLIDING_WINDOW
                    if overlap_prefix
                    else ChunkStrategyEnum.PARAGRAPH_MERGE
                )

                chunks.append(
                    self._create_chunk(
                        page=page,
                        section=section,
                        heading_path=heading_path,
                        chunk_index=chunk_idx,
                        text_content=full_chunk_text.strip(),
                        strategy=strategy,
                    )
                )

                if self.overlap_sentences > 0:
                    last_text = current_paragraphs[-1]
                    sentences = self._split_sentences(last_text)
                    overlap_prefix = " ".join(sentences[-self.overlap_sentences :])
                else:
                    overlap_prefix = ""

                chunk_idx += 1
                current_paragraphs = []
                current_tokens = estimate_token_count(overlap_prefix) if overlap_prefix else 0

        # Emit remaining paragraphs
        if current_paragraphs:
            body_text = "\n\n".join(current_paragraphs)
            full_chunk_text = f"{overlap_prefix}\n\n{body_text}" if overlap_prefix else body_text

            strategy = (
                ChunkStrategyEnum.SLIDING_WINDOW
                if overlap_prefix
                else ChunkStrategyEnum.PARAGRAPH_MERGE
            )

            chunks.append(
                self._create_chunk(
                    page=page,
                    section=section,
                    heading_path=heading_path,
                    chunk_index=chunk_idx,
                    text_content=full_chunk_text.strip(),
                    strategy=strategy,
                )
            )

        logger.debug(
            "generic_section_chunked",
            heading_path=heading_path,
            paragraphs=len(paragraphs),
            chunks_created=len(chunks),
        )

        return chunks
