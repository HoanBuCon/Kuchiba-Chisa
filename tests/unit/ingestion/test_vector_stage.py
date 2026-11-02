"""Vector stage: cache hits skip embedding, crashes keep progress, staging matches the corpus."""

import pytest

from app.application.ingestion.vector_stage import (
    VectorSettings,
    VectorStage,
    point_payload,
    staging_collection,
    vector_key,
)
from app.domain.ingestion.chunking import Chunk
from app.domain.ingestion.knowledge import KnowledgeBase, knowledge_counts
from app.domain.ingestion.units import Collection
from app.domain.interfaces.vectors import StagingError
from app.infrastructure.ingestion.gold.gold_store import FileGoldStore
from app.infrastructure.ingestion.gold.vector_cache import FileVectorCache

VERSION = "2026.11.02-1"
EMPTY = KnowledgeBase((), (), (), (), ())


def _chunk(number: int, collection: Collection = Collection.CANON) -> Chunk:
    return Chunk(
        evidence_id=f"wiki:1:{number}",
        point_id=f"point-{number}",
        page_id=1,
        title="T",
        family="lore",
        collection=collection,
        kind="prose",
        section=("S",),
        text=f"text {number}",
        embedding_text=f"passage: T\nS\ntext {number}",
        tokens=5,
        entities=("T",),
        nation="Huanglong",
        game_version="1.0",
    )


class FakeEmbedder:
    model_id = "model@1"
    dimension = 2

    def __init__(self, fail_after: int | None = None) -> None:
        self.embedded: list[str] = []
        self.fail_after = fail_after

    async def embed_passages(self, texts):
        if self.fail_after is not None and len(self.embedded) >= self.fail_after:
            raise RuntimeError("machine crashed")
        self.embedded.extend(texts)
        return [[float(len(text)), 1.0] for text in texts]


class FakeKnowledgeStore:
    def __init__(self, drop_rows: bool = False) -> None:
        self.published: dict[str, KnowledgeBase] = {}
        self.drop_rows = drop_rows

    async def publish(self, version, knowledge):
        self.published[version] = knowledge
        return knowledge_counts(knowledge)

    async def count(self, version):
        counts = knowledge_counts(self.published[version])
        return {**counts, "entities": counts["entities"] + 1} if self.drop_rows else counts


class FakeIndex:
    def __init__(self) -> None:
        self.created: dict[str, bool] = {}
        self.points: dict[str, list] = {}
        self.verified: dict[str, int] = {}

    async def create(self, collection, dimension, *, replace):
        self.created[collection] = replace
        self.points[collection] = []

    async def upsert(self, collection, points):
        self.points[collection].extend(points)

    async def verify(self, collection, expected_points):
        if len(self.points[collection]) != expected_points:
            raise StagingError("count")
        self.verified[collection] = expected_points


@pytest.fixture
def gold(tmp_path):
    store = FileGoldStore(tmp_path)
    chunks = [_chunk(1), _chunk(2), _chunk(3), _chunk(4, Collection.DIALOGUE)]
    store.write(VERSION, chunks, {}, EMPTY, {})
    return store


def _stage(tmp_path, gold, embedder, index=None, store=None, **settings) -> VectorStage:
    cache = FileVectorCache(tmp_path, embedder.model_id)
    return VectorStage(
        gold,
        embedder,
        cache,
        index or FakeIndex(),
        store or FakeKnowledgeStore(),
        VectorSettings(**settings),
    )


def test_gold_chunks_round_trip_and_latest_version_orders_numerically(tmp_path) -> None:
    store = FileGoldStore(tmp_path)
    store.write("2026.11.02-2", [_chunk(1)], {}, EMPTY, {})
    store.write("2026.11.02-10", [], {}, EMPTY, {})
    store.write("2026.11.01-99", [], {}, EMPTY, {})

    assert store.read_chunks("2026.11.02-2") == [_chunk(1)]
    assert store.latest_version() == "2026.11.02-10"


async def test_second_embed_only_touches_new_text(tmp_path, gold) -> None:
    first = await _stage(tmp_path, gold, FakeEmbedder(), embed_batch=2).embed(VERSION)
    repeat = FakeEmbedder()

    second = await _stage(tmp_path, gold, repeat).embed(VERSION)

    assert (first.embedded, first.cached) == (4, 0)
    assert (second.embedded, second.cached) == (0, 4)
    assert repeat.embedded == []


async def test_crash_keeps_flushed_vectors(tmp_path, gold) -> None:
    crashing = FakeEmbedder(fail_after=2)
    stage = _stage(tmp_path, gold, crashing, embed_batch=1, flush_every=1)
    with pytest.raises(RuntimeError):
        await stage.embed(VERSION)

    report = await _stage(tmp_path, gold, FakeEmbedder(), embed_batch=1).embed(VERSION)

    assert (report.cached, report.embedded) == (2, 2)


def test_vector_key_changes_with_model_and_text() -> None:
    assert vector_key("a", _chunk(1)) != vector_key("b", _chunk(1))
    assert vector_key("a", _chunk(1)) != vector_key("a", _chunk(2))


async def test_load_splits_collections_and_verifies_counts(tmp_path, gold) -> None:
    index = FakeIndex()
    stage = _stage(tmp_path, gold, FakeEmbedder(), index, upsert_batch=2)
    await stage.embed(VERSION)

    report = await stage.load(VERSION)

    assert report.collections == {
        "lore_canon__2026_11_02_1": 3,
        "lore_dialogue__2026_11_02_1": 1,
    }
    assert index.verified == report.collections
    point = index.points["lore_dialogue__2026_11_02_1"][0]
    assert point.point_id == "point-4"
    assert point.lexical_text == "text 4"
    assert point.vector == [pytest.approx(len(_chunk(4).embedding_text)), 1.0]


async def test_load_refuses_a_corpus_that_was_not_embedded(tmp_path, gold) -> None:
    with pytest.raises(KeyError):
        await _stage(tmp_path, gold, FakeEmbedder()).load(VERSION)


def test_payload_carries_the_knw003_metadata() -> None:
    payload = point_payload(_chunk(1), VERSION)

    assert payload["corpus_version"] == VERSION
    assert payload["source_kind"] == "wiki"
    assert payload["entities"] == ["T"]
    assert (payload["nation"], payload["game_version"]) == ("Huanglong", "1.0")
    assert payload["section_path"] == ["S"]
    assert staging_collection(Collection.CANON, VERSION) == "lore_canon__2026_11_02_1"


async def test_load_publishes_knowledge_and_reports_its_counts(tmp_path, gold) -> None:
    store = FakeKnowledgeStore()
    stage = _stage(tmp_path, gold, FakeEmbedder(), store=store)
    await stage.embed(VERSION)

    report = await stage.load(VERSION)

    assert store.published[VERSION] == EMPTY
    assert report.knowledge == knowledge_counts(EMPTY)


async def test_load_fails_when_stored_knowledge_differs_from_the_corpus(tmp_path, gold) -> None:
    stage = _stage(tmp_path, gold, FakeEmbedder(), store=FakeKnowledgeStore(drop_rows=True))
    await stage.embed(VERSION)

    with pytest.raises(StagingError, match="knowledge rows"):
        await stage.load(VERSION)
