"""Deterministic fusion of lore results returned from logical collections."""

from __future__ import annotations

from typing import Any

LoreResult = tuple[str, float, dict[str, Any]]


def fuse_lore_collection_buckets(
    collection_buckets: dict[str, list[LoreResult]],
) -> list[LoreResult]:
    """Apply the runtime cross-collection RRF and score fusion.

    Keeping this pure operation outside the route/pipeline coordinator lets
    production and evaluation execute one ranking implementation.
    """

    scored_by_text: dict[str, tuple[float, dict[str, Any]]] = {}
    for items in collection_buckets.values():
        for rank, (text, score, metadata) in enumerate(items, start=1):
            rrf_component = (1.0 / (60.0 + rank)) * 10.0
            fused_score = rrf_component + score
            evidence_metadata = {
                **metadata,
                "rrf_score": round(rrf_component, 6),
            }
            if text not in scored_by_text:
                scored_by_text[text] = (fused_score, evidence_metadata)
                continue

            existing_score, existing_metadata = scored_by_text[text]
            evidence_metadata["rrf_score"] = round(
                float(existing_metadata.get("rrf_score", 0.0)) + rrf_component,
                6,
            )
            scored_by_text[text] = (
                existing_score + fused_score,
                {**existing_metadata, **evidence_metadata},
            )

    fused = [(text, score, metadata) for text, (score, metadata) in scored_by_text.items()]
    fused.sort(key=lambda item: item[1], reverse=True)
    return fused
