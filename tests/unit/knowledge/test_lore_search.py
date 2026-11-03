"""`search_lore`: translation, entity channels, reranker fallback and typed evidence."""

from app.domain.ingestion.entity_linking import EntityLinker
from app.domain.ingestion.knowledge import Alias, Entity, KnowledgeBase
from app.domain.interfaces.reranker import (
    RerankerDataBoundary,
    RerankerFailureKind,
    RerankerUnavailableError,
)
from app.domain.services.knowledge.lore_search import (
    LoreHit,
    LoreSearchService,
    LoreSearchSettings,
    QueryTranslationError,
)


def _hit(number: int, title="Chisa", score=None) -> LoreHit:
    return LoreHit(
        evidence_id=f"wiki:1:{number}",
        page_id=1,
        title=title,
        text=f"text {number}",
        section_path=("Intro",),
        corpus_version="v1",
        source_kind="canon",
        score=score if score is not None else 1.0 / number,
        offset=number,
        url="https://w/Chisa",
        license="CC BY-SA",
        revid=7,
    )


class Translator:
    def __init__(self, reply="Where does Chisa study?", error=False) -> None:
        self.reply, self.error = reply, error

    async def to_english(self, question, budget=None):
        if self.error:
            raise QueryTranslationError("down")
        return self.reply


class Embedder:
    def __init__(self) -> None:
        self.calls = []

    async def embed_text(self, text, prefix="query: "):
        self.calls.append((text, prefix))
        return [0.1]


class Index:
    def __init__(self, hits) -> None:
        self.hits = hits
        self.calls = []

    async def search(self, text, vector, *, own_titles, mentioned, limit):
        self.calls.append((text, tuple(own_titles), tuple(mentioned), limit))
        return self.hits


class Reranker:
    data_boundary = RerankerDataBoundary.LOCAL

    def __init__(self, name="jina", scores=None, error=None) -> None:
        self.provider_name = name
        self.scores, self.error = scores, error
        self.documents = None

    async def rerank(self, query, documents):
        if self.error:
            raise RerankerUnavailableError("x", failure_kind=self.error)
        self.documents = documents
        return self.scores or [float(index) for index in range(len(documents))]


def _linker() -> EntityLinker:
    entities = (Entity(1, "Chisa", "resonator", {}, None, None, None, None),)
    aliases = (Alias("Thiên Tuế", "Chisa", "other_language", "high"),)
    return EntityLinker.from_knowledge(KnowledgeBase(entities, aliases, (), (), ()))


def _service(hits, translator=None, rerankers=None, settings=None, embedder=None):
    index = Index(hits)
    service = LoreSearchService(
        index,
        embedder or Embedder(),
        translator or Translator(),
        _linker(),
        rerankers if rerankers is not None else [Reranker()],
        settings,
    )
    return service, index


async def test_searches_with_the_translation_and_links_entities() -> None:
    service, index = _service([_hit(1)])

    result = await service.search("Chisa học ở đâu?")

    assert result.query == "Where does Chisa study?"
    assert index.calls == [("Where does Chisa study?", ("Chisa",), ("Chisa",), 50)]
    assert result.entities == ("Chisa",)
    assert result.degraded == ()


async def test_query_uses_the_e5_query_prefix() -> None:
    embedder = Embedder()
    service, _ = _service([_hit(1)], embedder=embedder)

    await service.search("Chisa?")

    assert embedder.calls == [("Where does Chisa study?", "query: ")]


async def test_vietnamese_alias_links_even_when_the_translation_drops_it() -> None:
    service, index = _service([_hit(1)], Translator("Where does she study?"))

    await service.search("Thiên Tuế học ở đâu?")

    assert index.calls[0][2] == ("Chisa",)


async def test_translation_failure_falls_back_to_the_question() -> None:
    service, index = _service([_hit(1)], Translator(error=True))

    result = await service.search("Chisa học ở đâu?")

    assert index.calls[0][0] == "Chisa học ở đâu?"
    assert result.degraded == ("translation_failed",)


async def test_no_entity_means_no_entity_channels() -> None:
    service, index = _service([_hit(1)], Translator("What is a Tacet Field?"))

    await service.search("Tacet Field là gì?")

    assert index.calls[0][1:3] == ((), ())


async def test_only_the_head_is_reranked_and_the_tail_keeps_its_order() -> None:
    hits = [_hit(n) for n in range(1, 5)]
    reranker = Reranker(scores=[0.1, 0.9])
    settings = LoreSearchSettings(rerank_candidates=2, top_k=4)
    service, _ = _service(hits, rerankers=[reranker], settings=settings)

    result = await service.search("Chisa?")

    assert [e.evidence_id for e in result.evidence] == [
        "wiki:1:2",
        "wiki:1:1",
        "wiki:1:3",
        "wiki:1:4",
    ]
    assert len(reranker.documents) == 2
    assert reranker.documents[0] == "Chisa\nIntro\ntext 1"


async def test_remote_failure_uses_the_local_fallback() -> None:
    remote = Reranker("jina", error=RerankerFailureKind.TIMEOUT)
    local = Reranker("local", scores=[1.0])
    service, _ = _service([_hit(1)], rerankers=[remote, local])

    result = await service.search("Chisa?")

    assert result.degraded == ("rerank_jina_timeout",)
    assert local.documents is not None


async def test_losing_every_reranker_keeps_the_fusion_order() -> None:
    remote = Reranker("jina", error=RerankerFailureKind.RATE_LIMIT)
    local = Reranker("local", error=RerankerFailureKind.UNAVAILABLE)
    service, _ = _service([_hit(1), _hit(2)], rerankers=[remote, local])

    result = await service.search("Chisa?")

    assert [e.evidence_id for e in result.evidence] == ["wiki:1:1", "wiki:1:2"]
    assert result.degraded[-1] == "rerank_skipped"


async def test_no_hits_returns_no_evidence() -> None:
    service, _ = _service([])

    result = await service.search("Chisa?")

    assert result.evidence == ()


async def test_evidence_carries_public_acl_and_provenance() -> None:
    service, _ = _service([_hit(3)])

    evidence = (await service.search("Chisa?")).evidence[0]

    assert evidence.access.scope == "public"
    assert evidence.kind == "lore"
    assert evidence.provenance.source_type == "canon"
    assert evidence.provenance.source_version == "v1"
    assert evidence.provenance.source_id == "https://w/Chisa"
    assert evidence.provenance.chunk_index == 3
