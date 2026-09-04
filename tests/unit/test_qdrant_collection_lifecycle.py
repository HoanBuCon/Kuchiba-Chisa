from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from qdrant_client.http.models import Distance, VectorParams

from app.infrastructure.vector.qdrant.qdrant_service import (
    CollectionAliasPromotionError,
    CollectionDimensionMismatchError,
    QdrantService,
    active_collection_alias,
)


def _collection_info(dimension: int) -> SimpleNamespace:
    return SimpleNamespace(
        config=SimpleNamespace(
            params=SimpleNamespace(
                vectors=VectorParams(size=dimension, distance=Distance.COSINE)
            )
        )
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
    alias_name = active_collection_alias("character_lore")
    client.get_aliases.return_value = SimpleNamespace(
        aliases=[SimpleNamespace(alias_name=alias_name, collection_name="character_lore__v1")]
    )
    service = QdrantService(client=client)

    result = await service.promote_active_alias(
        logical_collection="character_lore",
        target_collection="character_lore__v2",
        expected_point_count=17,
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
    service = QdrantService(client=client)

    with pytest.raises(CollectionAliasPromotionError, match="has 16 points; expected 17"):
        await service.promote_active_alias(
            logical_collection="character_lore",
            target_collection="character_lore__v2",
            expected_point_count=17,
            expected_dimension=384,
        )

    client.update_collection_aliases.assert_not_awaited()
    client.delete_collection.assert_not_awaited()


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
