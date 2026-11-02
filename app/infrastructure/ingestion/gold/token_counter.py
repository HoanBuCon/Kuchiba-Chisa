"""Count tokens with the embedding model's own tokenizer, so chunk limits are real (ING-004)."""

from __future__ import annotations

import hashlib
from pathlib import Path

from huggingface_hub import hf_hub_download
from tokenizers import Tokenizer

from app.domain.ingestion.chunking import TokenCounter

TOKENIZER_FILE = "tokenizer.json"


def _tokenizer_path(model_id: str, cache_dir: str | None) -> str:
    return hf_hub_download(model_id, TOKENIZER_FILE, cache_dir=cache_dir)


def tokenizer_sha256(model_id: str, cache_dir: str | None = None) -> str:
    """Recorded in the manifest: a changed tokenizer changes every token count."""
    return hashlib.sha256(Path(_tokenizer_path(model_id, cache_dir)).read_bytes()).hexdigest()


def load_token_counter(model_id: str, cache_dir: str | None = None) -> TokenCounter:
    tokenizer = Tokenizer.from_file(_tokenizer_path(model_id, cache_dir))
    # The model truncates; counting must see the full length to detect an overflow.
    tokenizer.no_truncation()

    def count(text: str) -> int:
        return len(tokenizer.encode(text).ids)

    return count
