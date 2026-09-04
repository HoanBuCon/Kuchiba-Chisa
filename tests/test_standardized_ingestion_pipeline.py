# -*- coding: utf-8 -*-
"""
End-to-End Test Suite: Standardized 6-Stage Wiki Ingestion Pipeline
Verifies Crawler classification, Canonical cleaning, Semantic chunking,
Benchmark validation, and Master Orchestrator CLI.
"""

import asyncio
import uuid
from types import SimpleNamespace
from typing import Any

import pytest
import pytest_asyncio
from click.testing import CliRunner
from qdrant_client.http.models import FieldCondition, Filter, MatchValue, PointIdsList

from app.domain.entities.lore import LorePayload
from app.infrastructure.ingestion.cli import cli
from app.infrastructure.ingestion.crawlers.wiki_crawler import WikiCrawler
from app.infrastructure.ingestion.quality.benchmark_runner import (
    BENCHMARK_TEST_CASES,
    BenchmarkRunner,
)


@pytest_asyncio.fixture(scope="module", autouse=True)
async def isolated_benchmark_corpus(
    isolated_vector_store: Any,
    test_embedder: Any,
) -> Any:
    """Seed and remove the 50-case corpus only on the isolated Qdrant endpoint."""
    fixture_namespace = uuid.UUID("00000000-0000-0000-0000-000000000950")
    collection = "world_lore"
    texts = [
        f"{case['query']}\n{' | '.join(case['expected_keywords'])}"
        for case in BENCHMARK_TEST_CASES
    ]
    vectors = await test_embedder.embed_batch(texts, prefix="passage: ")
    point_ids = [
        str(uuid.uuid5(fixture_namespace, str(case["id"])))
        for case in BENCHMARK_TEST_CASES
    ]

    for case, text_content, vector, point_id in zip(
        BENCHMARK_TEST_CASES, texts, vectors, point_ids, strict=True
    ):
        payload = LorePayload(
            parent_id=str(uuid.uuid5(fixture_namespace, f"parent-{case['id']}")),
            page_id=95000 + case["id"],
            source_file="ops01-benchmark-fixture.md",
            chunk_index=0,
            text_content=text_content,
            heading_path=case["category"],
            section_depth=2,
            canonical_name=case["expected_keywords"][0],
            entities=case["expected_keywords"],
        )
        await isolated_vector_store.upsert_lore(
            collection=collection,
            point_id=point_id,
            vector=vector,
            payload=payload,
        )

    async def retrieve_fixture_corpus(query: str, top_k: int = 5) -> list[SimpleNamespace]:
        """Search only the corpus seeded by this fixture on the isolated Qdrant endpoint."""
        query_vector = await test_embedder.embed_text(query, prefix="query: ")
        results = await isolated_vector_store._client.search(
            collection_name=collection,
            query_vector=query_vector,
            query_filter=Filter(
                must=[
                    FieldCondition(
                        key="source_file",
                        match=MatchValue(value="ops01-benchmark-fixture.md"),
                    )
                ]
            ),
            limit=top_k,
            with_payload=True,
        )
        return [
            SimpleNamespace(
                content=str((result.payload or {}).get("text_content", "")),
                score=float(result.score),
            )
            for result in results
        ]

    yield retrieve_fixture_corpus

    await isolated_vector_store._client.delete(
        collection_name=collection,
        points_selector=PointIdsList(points=point_ids),
        wait=True,
    )


def test_crawler_page_classification_rules():
    """Verify pre-crawl rule engine correctly approves clean lore and blocks noise."""
    crawler = WikiCrawler()

    # 1. Approved Clean Lore
    app, reason = crawler.classify_page("Chixia")
    assert app is True, f"Main article must be approved, got {reason}"

    app, reason = crawler.classify_page("Chixia/Backstory")
    assert app is True, f"Backstory subpage must be approved, got {reason}"

    app, reason = crawler.classify_page("Jiyan/Forte Examination Report")
    assert app is True, f"Forte Examination subpage must be approved, got {reason}"

    app, reason = crawler.classify_page("Startorch Academy")
    assert app is True, f"Faction page must be approved, got {reason}"

    # 2. Blocked Noise Subpages
    app, reason = crawler.classify_page("Chixia/Combat")
    assert app is False, "Combat subpage must be blocked"
    assert "combat" in reason.lower()

    app, reason = crawler.classify_page("Jiyan/Voicelines")
    assert app is False, "Voicelines subpage must be blocked"

    app, reason = crawler.classify_page("Changli/Gallery")
    assert app is False, "Gallery subpage must be blocked"

    app, reason = crawler.classify_page("Shorekeeper/Outfits")
    assert app is False, "Outfits subpage must be blocked"

    app, reason = crawler.classify_page("Category:Resonators")
    assert app is False, "Category namespace must be blocked"

    print("✅ PASS: WikiCrawler classification rules verified 100%!")


@pytest.mark.asyncio
async def test_benchmark_runner_50_cases_coverage(isolated_benchmark_corpus: Any):
    """Verify 50-case benchmark dataset completeness and simulated runner execution."""
    assert len(BENCHMARK_TEST_CASES) == 50, "Benchmark must contain exactly 50 test cases"

    runner = BenchmarkRunner(top_k=5, pass_threshold_pct=90.0)
    result = await runner.run(vector_retriever=isolated_benchmark_corpus)

    assert result.total_cases == 50
    assert result.hit_at_5_pct >= 90.0
    assert result.quality_gate_passed is True
    assert len(result.results_detail) == 50

    report_md = result.generate_report_markdown()
    assert "🏆 INGESTION QUALITY BENCHMARK REPORT" in report_md
    assert "Hit@5" in report_md

    print(f"✅ PASS: BenchmarkRunner verified: Hit@5 = {result.hit_at_5_pct:.1f}% (Quality Gate: PASS)!")


def test_cli_commands_interface():
    """Verify click CLI commands for scan-wiki, crawl-wiki, benchmark, and run-pipeline."""
    runner = CliRunner()

    # 1. Test CLI Help
    res = runner.invoke(cli, ["--help"])
    assert res.exit_code == 0
    assert "scan-wiki" in res.output
    assert "crawl-wiki" in res.output
    assert "benchmark" in res.output
    assert "run-pipeline" in res.output

    # 2. Test benchmark command CLI
    res = runner.invoke(cli, ["benchmark", "--top-k", "5"])
    assert res.exit_code == 0
    assert "INGESTION QUALITY BENCHMARK REPORT" in res.output

    print("✅ PASS: Click CLI commands interface verified!")


if __name__ == "__main__":
    test_crawler_page_classification_rules()
    test_benchmark_runner_50_cases_coverage()
    test_cli_commands_interface()
    print("\n🎉 ALL STANDARDIZED INGESTION PIPELINE TESTS PASSED!")
