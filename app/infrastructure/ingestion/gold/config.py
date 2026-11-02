"""Load the versioned corpus assembly settings (`app/config/ingestion/gold.yaml`)."""

from __future__ import annotations

import hashlib
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from app.application.ingestion.gold_stage import GoldSettings
from app.domain.ingestion.chunking import ChunkPolicy
from app.domain.ingestion.dedup import OwnerPolicy
from app.infrastructure.ingestion.wiki_sync_config import CONFIG_DIR


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class _Chunking(_Strict):
    target_tokens: int = Field(gt=0)
    max_tokens: int = Field(gt=0, le=512)
    min_tokens: int = Field(gt=0)
    overlap_turns: int = Field(ge=0)
    passage_prefix: str


class _Dedup(_Strict):
    min_chars: int = Field(gt=0)
    family_priority: tuple[str, ...] = Field(min_length=1)


class _Report(_Strict):
    tiny_chunk_tokens: int = Field(gt=0)


class _Gold(_Strict):
    version: int
    assembler_version: str = Field(min_length=1)
    tokenizer_model: str = Field(min_length=1)
    chunking: _Chunking
    dedup: _Dedup
    report: _Report


def load_gold_settings(path: Path = CONFIG_DIR / "gold.yaml") -> GoldSettings:
    text = path.read_text(encoding="utf-8")
    raw = _Gold.model_validate(yaml.safe_load(text))
    return GoldSettings(
        assembler_version=raw.assembler_version,
        config_hash=hashlib.sha256(text.encode("utf-8")).hexdigest()[:8],
        tokenizer_model=raw.tokenizer_model,
        chunk_policy=ChunkPolicy(**raw.chunking.model_dump()),
        owner_policy=OwnerPolicy(raw.dedup.family_priority, raw.dedup.min_chars),
        tiny_chunk_tokens=raw.report.tiny_chunk_tokens,
    )
