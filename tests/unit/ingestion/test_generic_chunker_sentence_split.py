"""Regression tests for GenericChunker's Python-compatible sentence splitter."""

from app.infrastructure.ingestion.chunkers.generic_chunker import GenericChunker


def test_sentence_splitter_preserves_known_abbreviations() -> None:
    chunker = GenericChunker()

    assert chunker._split_sentences("Dr. Honami arrived. The class started.") == [
        "Dr. Honami arrived.",
        "The class started.",
    ]
    assert chunker._split_sentences("No. 3 is active. Lv. 90 is required.") == [
        "No. 3 is active.",
        "Lv. 90 is required.",
    ]
