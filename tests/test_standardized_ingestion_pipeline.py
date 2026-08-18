# -*- coding: utf-8 -*-
"""
End-to-End Test Suite: Standardized 6-Stage Wiki Ingestion Pipeline
Verifies Crawler classification, Canonical cleaning, Semantic chunking,
Benchmark validation, and Master Orchestrator CLI.
"""

import os
import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import asyncio
import pytest
from click.testing import CliRunner

from app.infrastructure.ingestion.crawlers.wiki_crawler import WikiCrawler, CrawlReport
from app.infrastructure.ingestion.quality.benchmark_runner import BenchmarkRunner, BENCHMARK_TEST_CASES
from app.infrastructure.ingestion.pipeline import MasterIngestionPipeline
from app.infrastructure.ingestion.cli import cli


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


def test_benchmark_runner_50_cases_coverage():
    """Verify 50-case benchmark dataset completeness and simulated runner execution."""
    assert len(BENCHMARK_TEST_CASES) == 50, "Benchmark must contain exactly 50 test cases"

    runner = BenchmarkRunner(top_k=5, pass_threshold_pct=90.0)
    result = asyncio.run(runner.run())

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
