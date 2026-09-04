from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from qdrant_client.http.models import Distance, VectorParams

from app.domain.models.corpus_manifest import lore_manifest_checksum
from app.domain.models.corpus_release import CorpusRelease
from app.domain.models.lore_collections import LoreCollection
from app.infrastructure.vector.qdrant.qdrant_service import (
    AliasPromotionCandidate,
    CollectionAliasPromotionError,
    CollectionDimensionMismatchError,
    QdrantService,
    active_collection_alias,
)


def _collection_info(dimension: int) -> SimpleNamespace:
    return SimpleNamespace(
        config=SimpleNamespace(
            params=SimpleNamespace(
                vectors=VectorParams(size=dimension, distance=Distance.COSINE),
                sparse_vectors={"bm25": SimpleNamespace()},
            )
        )
    )


def _manifest_records(count: int, version: str = "v2") -> list[SimpleNamespace]:
    return [
        SimpleNamespace(
            id=f"point-{index}",
            payload={
                "chunk_hash": f"{index:064x}",
                "parent_id": f"parent-{index}",
                "source_id": "source-1",
                "corpus_version": version,
                "access_scope": "public",
            },
        )
        for index in range(count)
    ]


def _manifest_checksum(records: list[SimpleNamespace], version: str = "v2") -> str:
    rows = [
        QdrantService._manifest_row(
            point_id=str(record.id), payload=record.payload, corpus_version=version
        )
        for record in records
    ]
    return lore_manifest_checksum(rows)


def _candidate(target: str, count: int, records: list[SimpleNamespace]) -> AliasPromotionCandidate:
    return AliasPromotionCandidate(
        target_collection=target,
        expected_point_count=count,
        expected_corpus_version="v2",
        expected_manifest_checksum=_manifest_checksum(records),
    )


def _release() -> CorpusRelease:
    import uuid

    return CorpusRelease(
        job_id=uuid.uuid4(),
        source_id=uuid.uuid4(),
        logical_collection=LoreCollection.CHARACTER,
        staging_collection="character_lore__v2",
        corpus_version="v2",
        parent_count=1,
        vector_count=17,
        parent_manifest_checksum="a" * 64,
        vector_manifest_checksum=_manifest_checksum(_manifest_records(17)),
    )


@pytest.mark.asyncio
async def test_dimension_mismatch_never_deletes_or_recreates_collection() -> None:
    client = AsyncMock()
    client.get_collection.return_value = _collection_info(384)
    service = QdrantService(client=client)

    with pytest.raises(CollectionDimensionMismatchError, match="Create a versioned collection"):
        await service.create_collection("character_lore__v2", vector_size=1024)

    client.delete_collection.assert_not_awaited()
    client.create_collection.assert_not_awaited()


@pytest.mark.asyncio
async def test_active_collection_validation_is_read_only_and_detects_mismatch() -> None:
    client = AsyncMock()
    client.get_collection.return_value = _collection_info(384)
    service = QdrantService(client=client)

    readiness = await service.validate_active_collections(expected_dimension=1024)

    assert all(not result.ready for result in readiness.values())
    assert all(result.reason == "vector dimension mismatch" for result in readiness.values())
    client.create_collection.assert_not_awaited()
    client.delete_collection.assert_not_awaited()
    client.update_collection_aliases.assert_not_awaited()


@pytest.mark.asyncio
async def test_required_active_collections_fail_health_without_mutation() -> None:
    client = AsyncMock()
    client.get_collections.return_value = SimpleNamespace()
    client.get_collection.side_effect = RuntimeError("active alias missing")
    service = QdrantService(client=client)

    assert await service.health_check(require_active_collections=True) is False
    client.create_collection.assert_not_awaited()
    client.delete_collection.assert_not_awaited()


@pytest.mark.asyncio
async def test_alias_promotion_is_atomic_and_keeps_previous_collection() -> None:
    client = AsyncMock()
    client.get_collection.return_value = _collection_info(384)
    client.count.return_value = SimpleNamespace(count=17)
    records = _manifest_records(17)
    client.scroll.return_value = (records, None)
    alias_name = active_collection_alias("character_lore")
    client.get_aliases.return_value = SimpleNamespace(
        aliases=[SimpleNamespace(alias_name=alias_name, collection_name="character_lore__v1")]
    )
    service = QdrantService(client=client)

    result = await service.promote_active_alias(
        logical_collection="character_lore",
        target_collection="character_lore__v2",
        expected_point_count=17,
        expected_corpus_version="v2",
        expected_manifest_checksum=_manifest_checksum(records),
        expected_dimension=384,
    )

    assert result.previous_collection == "character_lore__v1"
    assert result.target_collection == "character_lore__v2"
    client.update_collection_aliases.assert_awaited_once()
    operations = client.update_collection_aliases.await_args.kwargs[
        "change_aliases_operations"
    ]
    assert len(operations) == 2
    assert operations[0].delete_alias.alias_name == alias_name
    assert operations[1].create_alias.alias_name == alias_name
    assert operations[1].create_alias.collection_name == "character_lore__v2"
    client.delete_collection.assert_not_awaited()


@pytest.mark.asyncio
async def test_alias_promotion_rejects_unverified_candidate_without_mutation() -> None:
    client = AsyncMock()
    client.get_collection.return_value = _collection_info(384)
    client.count.return_value = SimpleNamespace(count=16)
    records = _manifest_records(16)
    client.scroll.return_value = (records, None)
    service = QdrantService(client=client)

    with pytest.raises(CollectionAliasPromotionError, match="has 16 points; expected 17"):
        await service.promote_active_alias(
            logical_collection="character_lore",
            target_collection="character_lore__v2",
            expected_point_count=17,
            expected_corpus_version="v2",
            expected_manifest_checksum=_manifest_checksum(records),
            expected_dimension=384,
        )

    client.update_collection_aliases.assert_not_awaited()
    client.delete_collection.assert_not_awaited()


@pytest.mark.asyncio
async def test_alias_promotion_rejects_candidate_without_sparse_bm25_index() -> None:
    client = AsyncMock()
    client.get_collection.return_value = SimpleNamespace(
        config=SimpleNamespace(
            params=SimpleNamespace(
                vectors=VectorParams(size=384, distance=Distance.COSINE), sparse_vectors={}
            )
        )
    )
    service = QdrantService(client=client)
    records = _manifest_records(1)

    with pytest.raises(CollectionAliasPromotionError, match="sparse BM25"):
        await service.promote_active_alias(
            logical_collection="character_lore",
            target_collection="character_lore__v2",
            expected_point_count=1,
            expected_corpus_version="v2",
            expected_manifest_checksum=_manifest_checksum(records),
            expected_dimension=384,
        )

    client.count.assert_not_awaited()
    client.update_collection_aliases.assert_not_awaited()


@pytest.mark.asyncio
async def test_alias_set_promotion_validates_all_candidates_then_swaps_once() -> None:
    client = AsyncMock()
    client.get_collection.return_value = _collection_info(384)
    client.count.return_value = SimpleNamespace(count=17)
    records = _manifest_records(17)
    client.scroll.return_value = (records, None)
    client.get_aliases.return_value = SimpleNamespace(
        aliases=[
            SimpleNamespace(
                alias_name=active_collection_alias("character_lore"),
                collection_name="character_lore__v1",
            ),
            SimpleNamespace(
                alias_name=active_collection_alias("world_lore"),
                collection_name="world_lore__v1",
            ),
        ]
    )
    service = QdrantService(client=client)

    results = await service.promote_active_aliases(
        {
            "character_lore": _candidate("character_lore__v2", 17, records),
            "world_lore": _candidate("world_lore__v2", 17, records),
        },
        expected_dimension=384,
    )

    assert set(results) == {"character_lore", "world_lore"}
    assert results["character_lore"].previous_collection == "character_lore__v1"
    assert results["world_lore"].previous_collection == "world_lore__v1"
    client.update_collection_aliases.assert_awaited_once()
    operations = client.update_collection_aliases.await_args.kwargs[
        "change_aliases_operations"
    ]
    assert len(operations) == 4


@pytest.mark.asyncio
async def test_alias_promotion_rejects_incomplete_acl_before_alias_mutation() -> None:
    client = AsyncMock()
    client.get_collection.return_value = _collection_info(384)
    client.count.side_effect = [SimpleNamespace(count=17), SimpleNamespace(count=16)]
    records = _manifest_records(17)
    client.scroll.return_value = (records, None)
    service = QdrantService(client=client)

    with pytest.raises(CollectionAliasPromotionError, match="incomplete ACL"):
        await service.promote_active_alias(
            logical_collection="character_lore",
            target_collection="character_lore__v2",
            expected_point_count=17,
            expected_corpus_version="v2",
            expected_manifest_checksum=_manifest_checksum(records),
            expected_dimension=384,
        )

    client.update_collection_aliases.assert_not_awaited()


@pytest.mark.asyncio
async def test_alias_promotion_rejects_staged_payload_checksum_mismatch() -> None:
    client = AsyncMock()
    client.get_collection.return_value = _collection_info(384)
    client.count.return_value = SimpleNamespace(count=1)
    records = _manifest_records(1)
    records[0].payload["chunk_hash"] = "f" * 64
    client.scroll.return_value = (records, None)
    service = QdrantService(client=client)

    with pytest.raises(CollectionAliasPromotionError, match="manifest checksum mismatch"):
        await service.promote_active_alias(
            logical_collection="character_lore",
            target_collection="character_lore__v2",
            expected_point_count=1,
            expected_corpus_version="v2",
            expected_manifest_checksum=_manifest_checksum(_manifest_records(1)),
            expected_dimension=384,
        )

    client.update_collection_aliases.assert_not_awaited()


@pytest.mark.asyncio
async def test_release_publisher_rejects_missing_rollback_target_without_alias_mutation() -> None:
    client = AsyncMock()
    client.get_aliases.return_value = SimpleNamespace(aliases=[])
    service = QdrantService(client=client)

    with pytest.raises(CollectionAliasPromotionError, match="rollback target"):
        await service.promote(_release())

    client.update_collection_aliases.assert_not_awaited()


@pytest.mark.asyncio
async def test_release_publisher_promotes_only_the_verified_release_receipt() -> None:
    client = AsyncMock()
    client.get_collection.return_value = _collection_info(384)
    client.count.return_value = SimpleNamespace(count=17)
    records = _manifest_records(17)
    client.scroll.return_value = (records, None)
    alias_name = active_collection_alias("character_lore")
    client.get_aliases.return_value = SimpleNamespace(
        aliases=[SimpleNamespace(alias_name=alias_name, collection_name="character_lore__v1")]
    )
    service = QdrantService(client=client)

    publication = await service.promote(_release())

    assert publication.previous_active_collection == "character_lore__v1"
    assert publication.active_collection == "character_lore__v2"
    client.update_collection_aliases.assert_awaited_once()


@pytest.mark.asyncio
async def test_runtime_search_uses_the_active_alias_not_legacy_collection_name() -> None:
    client = AsyncMock()
    client.search.return_value = []
    service = QdrantService(client=client)

    await service.search_lore("character_lore", [0.1, 0.2])

    assert client.search.await_args.kwargs["collection_name"] == active_collection_alias(
        "character_lore"
    )


@pytest.mark.asyncio
async def test_lore_search_acl_filter_is_fail_closed_and_uses_trusted_scope_identifiers() -> None:
    client = AsyncMock()
    client.get_collection.return_value = _collection_info(384)
    client.search.return_value = []
    service = QdrantService(client=client)

    await service.search_lore(
        "character_lore",
        [0.1, 0.2],
        requester_subject_id="verified-user",
        requester_tenant_id="verified-tenant",
        requester_channel_id="verified-channel",
    )

    query_filter = client.search.await_args.kwargs["query_filter"]
    serialized_text = str(query_filter.model_dump(exclude_none=True))
    assert "access_scope" in serialized_text
    assert "verified-user" in serialized_text
    assert "verified-tenant" in serialized_text
    assert "verified-channel" in serialized_text
    assert "public" in serialized_text


@pytest.mark.asyncio
async def test_lore_search_without_private_context_allows_only_explicit_public_acl() -> None:
    client = AsyncMock()
    client.get_collection.return_value = _collection_info(384)
    client.search.return_value = []
    service = QdrantService(client=client)

    await service.search_lore("character_lore", [0.1, 0.2])

    serialized_text = str(
        client.search.await_args.kwargs["query_filter"].model_dump(exclude_none=True)
    )
    assert "public" in serialized_text
    assert "access_subject_id" not in serialized_text
    assert "access_tenant_id" not in serialized_text


@pytest.mark.asyncio
async def test_lifecycle_cli_dry_run_performs_no_qdrant_mutation() -> None:
    from scripts.manage_qdrant_alias import _build_parser, _run

    args = _build_parser().parse_args(
        [
            "promote",
            "--collection",
            "character_lore",
            "--target",
            "character_lore__v2",
            "--expected-point-count",
            "17",
            "--actor",
            "operator@example.test",
        ]
    )

    event = await _run(args)

    assert event["status"] == "dry_run"
    assert event["execute"] is False
    assert event["target_collection"] == "character_lore__v2"
