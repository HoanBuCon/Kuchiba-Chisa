"""
Quality Validation & Quarantine Management Package.

Implements §4.2 & §9 (5-Gate Quality Control System & Quarantine) of v1.1 Ingestion Architecture.

Modules:
    gates     — Individual Gate 1 to Gate 5 validators
    validator — Main QualityValidator engine & Quarantine Manager
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
]
