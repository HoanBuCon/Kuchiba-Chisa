"""Count tokens with the embedding model's own tokenizer, so chunk limits are real (ING-004)."""

from __future__ import annotations

from huggingface_hub import hf_hub_download
from tokenizers import Tokenizer

from app.domain.ingestion.chunking import TokenCounter


def load_token_counter(model_id: str, cache_dir: str | None = None) -> TokenCounter:
    tokenizer = Tokenizer.from_file(
        hf_hub_download(model_id, "tokenizer.json", cache_dir=cache_dir)
    )
    # The model truncates; counting must see the full length to detect an overflow.
    tokenizer.no_truncation()

    def count(text: str) -> int:
        return len(tokenizer.encode(text).ids)

    return count
