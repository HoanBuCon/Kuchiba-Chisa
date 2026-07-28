"""
Structure-Aware Chunkers Package.

Implements §8 (Chunk Planning Strategy) & §10 Stage 6 (CHUNK) of the Architecture Document v1.1.

Pipeline position:
    CanonicalPage (from canonical.jsonl)
                  ↓
       Structure-Aware Chunkers (PHA 4)
                  ↓
       Chunk (ready for Validate → Embed → Index)

Modules:
    base             — BaseChunker abstract strategy interface
    dialogue_chunker — Scene boundary chunker for quest & dialogue logs
    table_inliner    — Row-to-prose inlining chunker for structured tables
    generic_chunker  — H2/H3 hierarchy & sliding window paragraph chunker
"""

from app.infrastructure.ingestion.chunkers.base import BaseChunker
from app.infrastructure.ingestion.chunkers.dialogue_chunker import DialogueChunker
from app.infrastructure.ingestion.chunkers.generic_chunker import GenericChunker
from app.infrastructure.ingestion.chunkers.table_inliner import TableInlinerChunker

__all__ = [
    "BaseChunker",
    "DialogueChunker",
    "GenericChunker",
    "TableInlinerChunker",
    "chunk_canonical_page",
]


def chunk_canonical_page(
    page: "CanonicalPage",
    target_token_size: int = 256,
    max_token_size: int = 512,
    overlap_sentences: int = 0,
) -> list["Chunk"]:
    """
    Route a CanonicalPage to appropriate chunker strategies per section.

    Instantiates the right strategy for each section based on its ContentTypeEnum
    (TABLE -> TableInlinerChunker, DIALOGUE -> DialogueChunker, PROSE/LIST -> GenericChunker).

    Args:
        page: CanonicalPage instance from canonical layer.
        target_token_size: Target token size per chunk (default 256).
        max_token_size: Max token limit per chunk (default 512).
        overlap_sentences: Sentence overlap between consecutive chunks.

    Returns:
        List of retrieval-ready Chunk objects with inherited metadata and deterministic IDs.
    """
    chunks: list["Chunk"] = []

    dialogue_chunker = DialogueChunker(
        target_token_size=target_token_size,
        max_token_size=max_token_size,
    )
    table_chunker = TableInlinerChunker(
        target_token_size=target_token_size,
        max_token_size=max_token_size,
    )
    generic_chunker = GenericChunker(
        target_token_size=target_token_size,
        max_token_size=max_token_size,
        overlap_sentences=overlap_sentences,
    )

    from app.infrastructure.ingestion.models.canonical_page import ContentTypeEnum
    from app.infrastructure.ingestion.models.chunk_model import ChunkStrategyEnum

    # Traverse all sections recursively
    def _process_sections(sections: list["CanonicalSection"], heading_prefix: str) -> None:
        for sec in sections:
            heading_path = (
                f"{heading_prefix} > {sec.title}" if heading_prefix else f"{page.identity.title} > {sec.title}"
            )

            # Route by ContentTypeEnum
            if sec.content_type == ContentTypeEnum.TABLE:
                sec_chunks = table_chunker.chunk_section(page, sec, heading_path)
            elif sec.content_type == ContentTypeEnum.DIALOGUE:
                sec_chunks = dialogue_chunker.chunk_section(page, sec, heading_path)
            elif sec.content_type == ContentTypeEnum.HEADING_ONLY:
                sec_chunks = []
            elif sec.content_type == ContentTypeEnum.ATOMIC:
                # ATOMIC sections MUST NEVER be split
                if sec.content.strip():
                    sec_chunks = [
                        generic_chunker._create_chunk(
                            page=page,
                            section=sec,
                            heading_path=heading_path,
                            chunk_index=0,
                            text_content=sec.content.strip(),
                            strategy=ChunkStrategyEnum.ATOMIC,
                        )
                    ]
                else:
                    sec_chunks = []
            else:
                sec_chunks = generic_chunker.chunk_section(page, sec, heading_path)

            chunks.extend(sec_chunks)

            # Process subsections if any
            if sec.subsections:
                _process_sections(sec.subsections, heading_path)

    _process_sections(page.sections, "")
    return chunks
