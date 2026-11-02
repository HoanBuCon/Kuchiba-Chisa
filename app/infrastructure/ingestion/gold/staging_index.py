"""Qdrant staging collections: named dense vector, BM25 sparse channel, payload indexes (D11)."""

from __future__ import annotations

from collections.abc import Sequence

from qdrant_client import AsyncQdrantClient, models

from app.domain.interfaces.vectors import StagingError, StagingPoint

DENSE = "dense"
LEXICAL = "bm25"
LEXICAL_MODEL = "qdrant/bm25"
KEYWORD_INDEXES = (
    "access_scope",
    "entities",
    "entity_type",
    "page_type",
    "nation",
    "corpus_version",
)
INTEGER_INDEXES = ("page_id",)


class QdrantStagingIndex:
    def __init__(self, client: AsyncQdrantClient) -> None:
        self._client = client

    async def create(self, collection: str, dimension: int, *, replace: bool) -> None:
        if await self._client.collection_exists(collection):
            if not replace:
                raise StagingError(f"collection {collection} already exists")
            await self._client.delete_collection(collection)
        await self._client.create_collection(
            collection,
            vectors_config={
                DENSE: models.VectorParams(size=dimension, distance=models.Distance.COSINE)
            },
            sparse_vectors_config={
                LEXICAL: models.SparseVectorParams(modifier=models.Modifier.IDF)
            },
        )
        for field in KEYWORD_INDEXES:
            await self._client.create_payload_index(
                collection, field, models.PayloadSchemaType.KEYWORD
            )
        for field in INTEGER_INDEXES:
            await self._client.create_payload_index(
                collection, field, models.PayloadSchemaType.INTEGER
            )

    async def upsert(self, collection: str, points: Sequence[StagingPoint]) -> None:
        await self._client.upsert(
            collection,
            points=[
                models.PointStruct(
                    id=point.point_id,
                    vector={
                        DENSE: list(point.vector),
                        LEXICAL: models.Document(text=point.lexical_text, model=LEXICAL_MODEL),
                    },
                    payload=point.payload,
                )
                for point in points
            ],
            wait=True,
        )

    async def verify(self, collection: str, expected_points: int) -> None:
        info = await self._client.get_collection(collection)
        if LEXICAL not in (info.config.params.sparse_vectors or {}):
            raise StagingError(f"{collection} has no lexical channel")
        counted = (await self._client.count(collection, exact=True)).count
        if counted != expected_points:
            raise StagingError(f"{collection} holds {counted} points, expected {expected_points}")
