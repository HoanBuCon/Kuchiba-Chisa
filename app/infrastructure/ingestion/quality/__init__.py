"""
Quality Validation & Quarantine Management Package.

Modules:
    gates            — Individual Gate 1 to Gate 5 validators
    validator        — Main QualityValidator engine & Quarantine Manager
    benchmark_runner — Automated 50-case retrieval accuracy benchmark
"""

from app.infrastructure.ingestion.quality.gates import (
    Gate1StructureValidator,
    Gate2ContentValidator,
    Gate3EntityValidator,
    Gate4ChunkValidator,
    Gate5CorpusValidator,
    GateResult,
)
from app.infrastructure.ingestion.quality.validator import (
    QualityStatusEnum,
    QualityValidator,
    ValidationReport,
)
from app.infrastructure.ingestion.quality.benchmark_runner import (
    BenchmarkRunner,
    BenchmarkResult,
    BENCHMARK_TEST_CASES,
)

__all__ = [
    "Gate1StructureValidator",
    "Gate2ContentValidator",
    "Gate3EntityValidator",
    "Gate4ChunkValidator",
    "Gate5CorpusValidator",
    "GateResult",
    "QualityStatusEnum",
    "QualityValidator",
    "ValidationReport",
    "BenchmarkRunner",
    "BenchmarkResult",
    "BENCHMARK_TEST_CASES",
]
