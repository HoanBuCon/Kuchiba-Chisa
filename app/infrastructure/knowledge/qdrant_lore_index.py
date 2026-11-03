"""Lore retrieval in one Qdrant call, fused on the server with weighted RRF (ADV-004, PERF-007)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from qdrant_client import AsyncQdrantClient, models

from app.domain.services.knowledge.lore_search import LoreHit
from app.infrastructure.ingestion.gold.staging_index import DENSE, LEXICAL, LEXICAL_MODEL

PUBLIC_SCOPE = "public"
RRF_K = 60
PAYLOAD_FIELDS = [
    "evidence_id",
    "page_id",
    "title",
    "text",
    "section_path",
    "corpus_version",
    "source_kind",
    "offset",
    "url",
    "license",
    "revid",
]


@dataclass(frozen=True)
class ChannelWeights:
    dense: float = 1.0
    lexical: float = 1.0
    own_pages: float = 1.0
    mentions: float = 1.0


def _match_any(key: str, values: Sequence[str]) -> models.FieldCondition:
    return models.FieldCondition(key=key, match=models.MatchAny(any=list(values)))


def _public_and(*conditions: models.FieldCondition) -> models.Filter:
    """ACL is part of every query, so no later step can leak a private point."""
    scope = models.FieldCondition(key="access_scope", match=models.MatchValue(value=PUBLIC_SCOPE))
    return models.Filter(must=[scope, *conditions])


def _hit(point: Any) -> LoreHit:
    payload = point.payload
    return LoreHit(
        evidence_id=payload["evidence_id"],
        page_id=payload["page_id"],
        title=payload["title"],
        text=payload["text"],
        section_path=tuple(payload.get("section_path") or ()),
        corpus_version=payload["corpus_version"],
        source_kind=payload["source_kind"],
        score=point.score,
        offset=payload.get("offset", 0),
        url=payload.get("url", ""),
        license=payload.get("license", ""),
        revid=payload.get("revid", 0),
    )


class QdrantLoreIndex:
    def __init__(
        self,
        client: AsyncQdrantClient,
        collection: str,
        weights: ChannelWeights | None = None,
    ) -> None:
        self._client = client
        self._collection = collection
        self._weights = weights or ChannelWeights()

    def _channels(
        self,
        text: str,
        vector: Sequence[float],
        own_titles: Sequence[str],
        mentioned: Sequence[str],
        limit: int,
    ) -> tuple[list[models.Prefetch], list[float]]:
        def dense(query_filter: models.Filter) -> models.Prefetch:
            return models.Prefetch(
                query=list(vector), using=DENSE, filter=query_filter, limit=limit
            )

        weights = self._weights
        lexical = models.Prefetch(
            query=models.Document(text=text, model=LEXICAL_MODEL),
            using=LEXICAL,
            filter=_public_and(),
            limit=limit,
        )
        channels = [dense(_public_and()), lexical]
        channel_weights = [weights.dense, weights.lexical]
        if own_titles:
            channels.append(dense(_public_and(_match_any("title", own_titles))))
            channel_weights.append(weights.own_pages)
        if mentioned:
            channels.append(dense(_public_and(_match_any("entities", mentioned))))
            channel_weights.append(weights.mentions)
        return channels, channel_weights

    async def search(
        self,
        text: str,
        vector: Sequence[float],
        *,
        own_titles: Sequence[str],
        mentioned: Sequence[str],
        limit: int,
    ) -> list[LoreHit]:
        channels, weights = self._channels(text, vector, own_titles, mentioned, limit)
        response = await self._client.query_points(
            self._collection,
            prefetch=channels,
            query=models.RrfQuery(rrf=models.Rrf(k=RRF_K, weights=weights)),
            limit=limit,
            with_payload=PAYLOAD_FIELDS,
        )
        return [_hit(point) for point in response.points]
