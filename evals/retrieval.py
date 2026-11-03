"""Retrieval-level evaluation of a staged corpus: no LLM, safe to run on every release (S8).

Usage: python -m evals.retrieval --version 2026.11.02-7 [--mode hybrid] [--report out.json]
`--gate` judges the free `translated_local` mode against gates.yaml; `--active` is the live report.
Modes ending in `reranked` spend prepaid Jina tokens; `all` never does.
`translated` modes search with frozen English questions (ADV-010), so they call no LLM.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import yaml
from fastembed.rerank.cross_encoder import TextCrossEncoder
from qdrant_client import AsyncQdrantClient, models

from app.application.ingestion.vector_stage import staging_collection
from app.config.settings import settings
from app.domain.ingestion.entity_linking import EntityLinker
from app.domain.ingestion.release_gates import GateReport, evaluate_retrieval_gate
from app.domain.ingestion.text_normalization import normalize_text
from app.domain.ingestion.units import Collection
from app.infrastructure.embeddings.fastembed_adapter import FastEmbedAdapter
from app.infrastructure.ingestion.gates_config import load_gate_policies
from app.infrastructure.ingestion.gold.gold_store import FileGoldStore
from app.infrastructure.ingestion.gold.staging_index import DENSE, LEXICAL, LEXICAL_MODEL
from app.infrastructure.rag.api_cross_encoder_reranker import (
    ApiCrossEncoderReranker,
    ApiRerankerProvider,
)
from evals.dataset import GoldenCase, Language, load_golden_set
from evals.metrics import hit_at_k, reciprocal_rank, wilson_interval

GOLDEN_PATH = Path("data/evaluations/golden_v2/golden_v2.yaml")
TRANSLATIONS_PATH = Path("data/evaluations/golden_v2/query_translations.yaml")
HIT_K = 5
RANK_K = 10
CANDIDATES = 50
RRF_K = 60
EMBED_THREADS = 2
LINKED = "linked"
TRANSLATED = "translated"
TRANSLATED_LOCAL = "translated_local"
MODES = ("dense", "lexical", "hybrid", LINKED, TRANSLATED, TRANSLATED_LOCAL)
RERANKED = "reranked"
TRANSLATED_RERANKED = "translated_reranked"
PAID_MODES = (RERANKED, TRANSLATED_RERANKED)
TRANSLATED_MODES = (TRANSLATED, TRANSLATED_LOCAL, TRANSLATED_RERANKED)
GATE_MODE = TRANSLATED_LOCAL
# On translated questions 50 candidates beat 15 and 30 on the dev half, at about 3x the tokens.
RERANK_MODEL = "jina-reranker-v3"
RERANK_CANDIDATES = 50
# Free and good enough to gate a release; deeper candidates scored no better and cost time.
LOCAL_RERANK_MODEL = "Xenova/ms-marco-MiniLM-L-6-v2"
LOCAL_RERANK_CANDIDATES = 15
LOCAL_RERANK_BATCH = 8
RERANK_TIMEOUT_SECONDS = 30
# Paced to stay under the key's tokens-per-minute limit, which otherwise skews results.
RERANK_PAUSE_SECONDS = 13


@dataclass(frozen=True)
class CaseOutcome:
    case_id: str
    category: str
    language: str
    question: str
    relevant: tuple[int, ...]
    ranked: tuple[int, ...]
    hit: bool
    reciprocal: float


def load_translations(path: Path) -> dict[str, str]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {} if path.exists() else {}


def search_query(case: GoldenCase, question: str, translations: Mapping[str, str]) -> str:
    """English questions search as asked; a missing translation stops the run, not skews it."""
    if case.language is Language.EN:
        return question
    if case.id not in translations:
        raise SystemExit(f"{case.id} has no frozen translation; run evals.translate_queries")
    return normalize_text(translations[case.id])


def ranked_pages(points: Sequence[Any]) -> list[int]:
    """Chunks of one page count once, so a long page cannot fill the top results alone."""
    return list(dict.fromkeys(point.payload["page_id"] for point in points))


def fuse_ranked(result_lists: Sequence[Sequence[Any]], k: int = RRF_K) -> list[Any]:
    """Reciprocal rank fusion across collections, whose raw scores are not comparable."""
    scores: dict[Any, float] = defaultdict(float)
    points: dict[Any, Any] = {}
    for results in result_lists:
        for rank, point in enumerate(results, start=1):
            scores[point.id] += 1.0 / (k + rank)
            points[point.id] = point
    return [points[point_id] for point_id in sorted(scores, key=lambda p: -scores[p])]


def rerank_order(points: Sequence[Any], scores: Sequence[float]) -> list[Any]:
    """Scored head first by score; candidates beyond the reranker's reach keep their order."""
    head = sorted(range(len(scores)), key=lambda index: -scores[index])
    return [points[index] for index in head] + list(points[len(scores) :])


def rerank_document(point: Any) -> str:
    payload = point.payload
    section = " > ".join(payload.get("section_path") or [])
    return f"{payload['title']}\n{section}\n{payload['text']}"


def score_case(case: GoldenCase, question: str, ranked: Sequence[int]) -> CaseOutcome:
    relevant = {page.pageid for page in case.relevant_pages}
    return CaseOutcome(
        case_id=case.id,
        category=case.category.value,
        language=case.language.value,
        question=question,
        relevant=tuple(sorted(relevant)),
        ranked=tuple(ranked[:RANK_K]),
        hit=hit_at_k(ranked, relevant, HIT_K),
        reciprocal=reciprocal_rank(ranked, relevant, RANK_K),
    )


def _group(outcomes: Sequence[CaseOutcome]) -> dict[str, Any]:
    hits = sum(outcome.hit for outcome in outcomes)
    low, high = wilson_interval(hits, len(outcomes)) if outcomes else (0.0, 0.0)
    return {
        "cases": len(outcomes),
        "hit_at_5": round(hits / len(outcomes), 3) if outcomes else None,
        "hit_at_5_ci95": [round(low, 3), round(high, 3)],
        "mrr_at_10": round(statistics.mean(o.reciprocal for o in outcomes), 3)
        if outcomes
        else None,
    }


def summarize(outcomes: Sequence[CaseOutcome]) -> dict[str, Any]:
    by_category: dict[str, list[CaseOutcome]] = defaultdict(list)
    by_language: dict[str, list[CaseOutcome]] = defaultdict(list)
    for outcome in outcomes:
        by_category[outcome.category].append(outcome)
        by_language[outcome.language].append(outcome)
    return {
        "overall": _group(outcomes),
        "by_category": {name: _group(group) for name, group in sorted(by_category.items())},
        "by_language": {name: _group(group) for name, group in sorted(by_language.items())},
    }


class StagedCorpusSearch:
    """Canon only by default (ADV-005); `linked` adds the entity channels of ADV-002."""

    def __init__(self, client: AsyncQdrantClient, version: str, linker: EntityLinker) -> None:
        self._client = client
        self._collection = staging_collection(Collection.CANON, version)
        self._linker = linker

    async def _query(self, query: Any, using: str, query_filter: Any = None) -> list[Any]:
        response = await self._client.query_points(
            self._collection,
            query=query,
            using=using,
            query_filter=query_filter,
            limit=CANDIDATES,
            with_payload=["page_id", "title", "text", "section_path"],
        )
        return list(response.points)

    async def _dense(self, vector: Sequence[float], query_filter: Any = None) -> list[Any]:
        return await self._query(list(vector), DENSE, query_filter)

    async def _lexical(self, text: str) -> list[Any]:
        return await self._query(models.Document(text=text, model=LEXICAL_MODEL), LEXICAL)

    async def _entity_channels(self, text: str, vector: Sequence[float]) -> list[list[Any]]:
        entities = self._linker.link(text)
        if not entities:
            return []
        own = _any_of("title", self._linker.own_pages(entities))
        mentions = _any_of("entities", entities)
        return [await self._dense(vector, own), await self._dense(vector, mentions)]

    async def search(self, mode: str, text: str, vector: Sequence[float]) -> list[Any]:
        if mode == "dense":
            return await self._dense(vector)
        if mode == "lexical":
            return await self._lexical(text)
        channels = [await self._dense(vector), await self._lexical(text)]
        if mode in {LINKED, RERANKED}:
            channels.extend(await self._entity_channels(text, vector))
        return fuse_ranked(channels)


def _any_of(field: str, values: Sequence[str]) -> models.Filter:
    condition = models.FieldCondition(key=field, match=models.MatchAny(any=list(values)))
    return models.Filter(must=[condition])


async def evaluate(version: str, mode: str) -> tuple[dict[str, Any], list[CaseOutcome]]:
    golden = load_golden_set(GOLDEN_PATH)
    knowledge = FileGoldStore(Path(settings.INGESTION_DATA_DIR)).read_knowledge(version)
    embedder = FastEmbedAdapter(threads=EMBED_THREADS)
    client = AsyncQdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY, timeout=60)
    search = StagedCorpusSearch(client, version, EntityLinker.from_knowledge(knowledge))
    outcomes = []
    http = httpx.AsyncClient()
    reranker: Any = _jina_reranker(http) if mode in PAID_MODES else None
    if mode == TRANSLATED_LOCAL:
        reranker = _LocalReranker()
    depth = LOCAL_RERANK_CANDIDATES if mode == TRANSLATED_LOCAL else RERANK_CANDIDATES
    pause = 0 if mode == TRANSLATED_LOCAL else RERANK_PAUSE_SECONDS
    translated = mode in TRANSLATED_MODES
    translations = load_translations(TRANSLATIONS_PATH) if translated else {}
    try:
        for case in golden.cases:
            if not case.relevant_pages:
                continue
            question = normalize_text(case.turns[-1].message)
            query = search_query(case, question, translations) if translated else question
            vector = await embedder.embed_text(query, prefix="query: ")
            points = await search.search(LINKED if translated else mode, query, vector)
            if reranker is not None:
                head = points[:depth]
                scores = await reranker.rerank(query, [rerank_document(p) for p in head])
                points = rerank_order(points, scores)
                await asyncio.sleep(pause)
            outcomes.append(score_case(case, question, ranked_pages(points)))
    finally:
        await client.close()
        await http.aclose()
    summary = summarize(outcomes)
    summary["verified_cases"] = sum(c.verified and bool(c.relevant_pages) for c in golden.cases)
    return summary, outcomes


class _LocalReranker:
    """Runs in-process for the gate; the runtime uses local models via the inference service."""

    def __init__(self) -> None:
        self._model = TextCrossEncoder(LOCAL_RERANK_MODEL, threads=EMBED_THREADS)

    async def rerank(self, query: str, documents: list[str]) -> list[float]:
        scores = self._model.rerank(query, documents, batch_size=LOCAL_RERANK_BATCH)
        return list(scores)


def _jina_reranker(http: httpx.AsyncClient) -> ApiCrossEncoderReranker:
    if not settings.JINA_API_KEY:
        raise SystemExit("reranked mode needs JINA_API_KEY")
    return ApiCrossEncoderReranker(
        provider=ApiRerankerProvider.JINA,
        api_key=settings.JINA_API_KEY,
        model_name=RERANK_MODEL,
        timeout_seconds=RERANK_TIMEOUT_SECONDS,
        max_documents=RERANK_CANDIDATES,
        http_client=http,
    )


def _selected_modes(args: argparse.Namespace) -> Sequence[str]:
    if args.gate:
        return (GATE_MODE,)
    return MODES if args.mode == "all" else (args.mode,)


def _retrieval_gate(
    summary: dict[str, Any], outcomes: Sequence[CaseOutcome], active_report: str | None
) -> GateReport:
    _, policy = load_gate_policies()
    active = None
    if active_report:
        report = json.loads(Path(active_report).read_text(encoding="utf-8"))
        active = report["modes"][GATE_MODE]
    return evaluate_retrieval_gate(summary, {o.case_id for o in outcomes if o.hit}, active, policy)


async def _main(args: argparse.Namespace) -> int:
    report: dict[str, Any] = {"corpus_version": args.version, "modes": {}, "misses": {}}
    gate: GateReport | None = None
    for mode in _selected_modes(args):
        started = time.perf_counter()
        summary, outcomes = await evaluate(args.version, mode)
        summary["seconds"] = round(time.perf_counter() - started, 1)
        report["modes"][mode] = summary
        report["misses"][mode] = [
            {
                "id": o.case_id,
                "category": o.category,
                "question": o.question,
                "relevant": o.relevant,
                "top": o.ranked[:5],
            }
            for o in outcomes
            if not o.hit
        ]
        if args.gate:
            gate = _retrieval_gate(summary, outcomes, args.active)
    if gate is not None:
        report["gate"] = {
            "passed": gate.passed,
            "failures": list(gate.failures),
            "checks": {check.name: check.detail for check in gate.checks},
        }
    text = json.dumps(report, ensure_ascii=False, indent=1)
    if args.report:
        Path(args.report).write_text(text, encoding="utf-8")
    # Questions are Vietnamese, which a legacy Windows console codec cannot print.
    sys.stdout.buffer.write((text + "\n").encode("utf-8"))
    return 1 if gate is not None and not gate.passed else 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="evals.retrieval", description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--mode", choices=(*MODES, *PAID_MODES, "all"), default="all")
    parser.add_argument("--report", help="also write the JSON report to this path")
    parser.add_argument("--gate", action="store_true", help="exit 1 unless the gate passes")
    parser.add_argument("--active", help="retrieval report of the active release")
    return asyncio.run(_main(parser.parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
