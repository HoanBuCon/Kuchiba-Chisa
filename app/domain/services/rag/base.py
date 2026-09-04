from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.domain.models.evidence import (
    Evidence,
    EvidenceAccess,
    EvidenceProvenance,
    EvidenceScore,
)


def lore_evidence(
    *, text: str, final_score: float, metadata: dict[str, Any]
) -> Evidence:
    """Create public lore evidence from the Qdrant record retained by the retriever."""

    source_id = str(
        metadata.get("point_id")
        or metadata.get("chunk_id")
        or metadata.get("parent_id")
        or (
            f"{metadata.get('collection', 'lore')}:"
            f"{metadata.get('page_id', 'unknown')}:"
            f"{metadata.get('chunk_index', 0)}"
        )
    )
    components = {
        key: float(value)
        for key, value in metadata.items()
        if key
        in {
            "dense_score",
            "dense_sparse_rrf_score",
            "keyword_score",
            "metadata_score",
            "rrf_score",
            "sparse_score",
            "vector_score",
            "hybrid_score",
        }
        and isinstance(value, int | float)
    }
    return Evidence(
        evidence_id=f"lore:{source_id}",
        kind="lore",
        text=text,
        provenance=EvidenceProvenance(
            source_id=source_id,
            source_type=str(metadata.get("source_type") or "lore"),
            collection=str(metadata.get("collection") or "lore"),
            source_version=_source_version(metadata),
            parent_id=_optional_string(metadata.get("parent_id")),
            page_id=_optional_int(metadata.get("page_id")),
            section_id=_optional_string(metadata.get("section_id")),
            chunk_index=_optional_int(metadata.get("chunk_index")),
            chunk_start_offset=_optional_int(metadata.get("chunk_start_offset")),
            chunk_end_offset=_optional_int(metadata.get("chunk_end_offset")),
        ),
        access=EvidenceAccess(
            scope=str(metadata.get("access_scope") or "public"),
            subject_id=_optional_string(metadata.get("access_subject_id")),
            tenant_id=_optional_string(metadata.get("access_tenant_id")),
            channel_id=_optional_string(metadata.get("access_channel_id")),
        ),
        score=EvidenceScore(final=float(final_score), components=components),
    )


def memory_evidence(
    *, memory: ScoredMemory, kind: Literal["memory", "guild_memory"], access: EvidenceAccess
) -> Evidence:
    """Create tenant-scoped evidence without trusting retrieved text for identity."""

    metadata = memory.metadata
    source_id = memory.id
    return Evidence(
        evidence_id=f"{kind}:{source_id}",
        kind=kind,
        text=memory.text_content,
        provenance=EvidenceProvenance(
            source_id=source_id,
            source_type=memory.memory_type,
            collection=str(
                metadata.get("collection")
                or ("memories" if kind == "memory" else "guild_memories")
            ),
            source_version=_source_version(metadata),
            parent_id=_optional_string(metadata.get("parent_id")),
            page_id=_optional_int(metadata.get("page_id")),
            section_id=_optional_string(metadata.get("section_id")),
            chunk_index=_optional_int(metadata.get("chunk_index")),
            chunk_start_offset=_optional_int(metadata.get("chunk_start_offset")),
            chunk_end_offset=_optional_int(metadata.get("chunk_end_offset")),
        ),
        access=access,
        score=EvidenceScore(final=memory.final_score, components=dict(memory.components)),
    )


def image_memory_evidence(*, image: dict[str, Any], user_id: str) -> Evidence:
    """Represent image retrieval by caption/provenance only; never carry URL or local path."""

    image_id = str(image["image_id"])
    guild_id = _optional_string(image.get("guild_id"))
    return Evidence(
        evidence_id=f"image_memory:{image_id}",
        kind="image_memory",
        text=str(image.get("visual_caption") or image_id),
        provenance=EvidenceProvenance(
            source_id=image_id,
            source_type="image_memory",
            collection="image_memories",
            source_version=_optional_string(image.get("source_version")),
        ),
        access=(
            EvidenceAccess(
                scope="tenant",
                tenant_id=guild_id,
                channel_id=_optional_string(image.get("channel_id")),
            )
            if guild_id
            else EvidenceAccess(scope="user", subject_id=user_id)
        ),
        score=EvidenceScore(
            final=float(image.get("score", 0.0)),
            components={"similarity": float(image.get("score", 0.0))},
        ),
    )


def _source_version(metadata: dict[str, Any]) -> str | None:
    """Use an indexed source version when present; do not invent one for legacy records."""

    value = metadata.get("source_version")
    if value is None:
        value = metadata.get("revision_id")
    return str(value) if value is not None else None


def _optional_string(value: Any) -> str | None:
    return str(value) if value is not None and str(value) else None


def _optional_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None

class ScoredMemory(BaseModel):
    id: str
    text_content: str
    memory_type: str
    memory_tier: str
    final_score: float
    metadata: dict[str, Any] = Field(default_factory=dict)
    components: dict[str, float]


class RAGContext(BaseModel):
    lore_chunks: list[str] = Field(default_factory=list)
    memories: list[str] = Field(default_factory=list)
    guild_memories: list[str] = Field(default_factory=list)
    retrieved_images: list[dict[str, Any]] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    tool_output_msg: str = ""
    is_aligned: bool = True
    alignment_reason: str = ""
    thinking_steps: list[dict[str, Any]] = Field(default_factory=list)
