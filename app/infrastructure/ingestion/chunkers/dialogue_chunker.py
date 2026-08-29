"""
Dialogue Chunker — Scene Boundary aware chunking for quest & dialogue logs (§8.2).

Strategy:
    1. Groups consecutive speaker turns into scene blocks.
    2. Guarantees dialogue lines are NEVER split mid-sentence or mid-turn.
    3. Preserves speaker attribution (Speaker: "Quote") on every turn.
    4. Automatically extracts speaker names as chunk entities.
    5. Prefixes dialogue chunks with context metadata (Quest/Scene context).
    6. Uses ChunkStrategyEnum.SCENE_BOUNDARY.
"""

from __future__ import annotations

import re
from typing import List, Tuple, Set

import structlog

from app.infrastructure.ingestion.chunkers.base import BaseChunker
from app.infrastructure.ingestion.models.canonical_page import CanonicalPage, CanonicalSection
from app.infrastructure.ingestion.models.chunk_model import Chunk, ChunkStrategyEnum, estimate_token_count

logger = structlog.get_logger(__name__)

# Matches line with speaker attribution: "Speaker: Quote", "[Speaker]: ...", supporting Unicode
_RE_SPEAKER_LINE = re.compile(r"^\[?([A-ZÀ-Ỹ][a-zA-ZÀ-ỹ0-9_\s\.\-]{1,30})\]?:\s*(.+)$")


class DialogueChunker(BaseChunker):
    """
    Chunker implementation for DIALOGUE content types.

    Preserves speaker turns and groups conversation exchanges into scenes.
    """

    def _parse_speaker_turns(self, text: str) -> List[Tuple[str, str, str]]:
        """
        Parse raw section content into structured speaker turns.

        Returns:
            List of tuples: (speaker_name, dialogue_text, original_line)
        """
        turns: List[Tuple[str, str, str]] = []
        for line in text.split("\n"):
            line_str = line.strip()
            if not line_str:
                continue

            match = _RE_SPEAKER_LINE.match(line_str)
            if match:
                speaker = match.group(1).strip()
                dialogue = match.group(2).strip()
                turns.append((speaker, dialogue, line_str))
            else:
                if turns and turns[-1][0] != "Narrator" and not line_str.startswith(("---", "***", "===")):
                    prev_spk, prev_diag, prev_raw = turns[-1]
                    turns[-1] = (prev_spk, f"{prev_diag} {line_str}", f"{prev_raw}\n{line_str}")
                else:
                    # Narration or non-attributed line
                    turns.append(("Narrator", line_str, line_str))

        return turns

    def chunk_section(
        self,
        page: CanonicalPage,
        section: CanonicalSection,
        heading_path: str,
    ) -> List[Chunk]:
        """
        Chunk a dialogue section into scene boundary chunks.

        Args:
            page: Parent CanonicalPage.
            section: Section to chunk.
            heading_path: Full heading path.

        Returns:
            List of retrieval-ready Chunk objects with SCENE_BOUNDARY strategy.
        """
        if not section.content.strip():
            return []

        turns = self._parse_speaker_turns(section.content)
        if not turns:
            return []

        chunks: List[Chunk] = []
        current_turn_lines: List[str] = []
        current_speakers: Set[str] = set()
        current_tokens = 0
        chunk_idx = 0

        for speaker, dialogue, full_line in turns:
            line_tokens = estimate_token_count(full_line)

            # Check if adding this turn exceeds max_token_size
            if current_turn_lines and (current_tokens + line_tokens > self.max_token_size):
                # Emit current scene chunk
                scene_text = "\n".join(current_turn_lines)
                entities = sorted(list(current_speakers | set(section.entities_in_section)))

                chunks.append(
                    self._create_chunk(
                        page=page,
                        section=section,
                        heading_path=heading_path,
                        chunk_index=chunk_idx,
                        text_content=scene_text,
                        strategy=ChunkStrategyEnum.SCENE_BOUNDARY,
                        entities_override=entities,
                    )
                )

                chunk_idx += 1
                current_turn_lines = []
                current_speakers = set()
                current_tokens = 0

            # Add turn to current scene
            current_turn_lines.append(full_line)
            if speaker != "Narrator":
                current_speakers.add(speaker)
            current_tokens += line_tokens

            # Target token size reached -> check if natural scene end (topic shift or speaker pause)
            if current_tokens >= self.target_token_size and len(current_turn_lines) >= 3:
                scene_text = "\n".join(current_turn_lines)
                entities = sorted(list(current_speakers | set(section.entities_in_section)))

                chunks.append(
                    self._create_chunk(
                        page=page,
                        section=section,
                        heading_path=heading_path,
                        chunk_index=chunk_idx,
                        text_content=scene_text,
                        strategy=ChunkStrategyEnum.SCENE_BOUNDARY,
                        entities_override=entities,
                    )
                )

                chunk_idx += 1
                current_turn_lines = []
                current_speakers = set()
                current_tokens = 0

        # Emit remaining turns if any
        if current_turn_lines:
            scene_text = "\n".join(current_turn_lines)
            entities = sorted(list(current_speakers | set(section.entities_in_section)))

            chunks.append(
                self._create_chunk(
                    page=page,
                    section=section,
                    heading_path=heading_path,
                    chunk_index=chunk_idx,
                    text_content=scene_text,
                    strategy=ChunkStrategyEnum.SCENE_BOUNDARY,
                    entities_override=entities,
                )
            )

        logger.debug(
            "dialogue_section_chunked",
            heading_path=heading_path,
            turns=len(turns),
            chunks_created=len(chunks),
        )

        return chunks
