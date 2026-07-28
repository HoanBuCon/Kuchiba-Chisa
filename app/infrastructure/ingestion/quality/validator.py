"""
QualityValidator Engine & Quarantine Manager (§4.2 & §9).

Coordinates 5-Gate Quality Control validation, computes composite quality scores,
and isolates low-confidence pages (< 0.5 quality_score) into the Quarantine directory.

Score Categories:
    - > 0.8:   AUTO_APPROVED (Passed cleanly)
    - 0.5–0.8: APPROVED_WITH_WARNINGS (Logged with warnings, indexed)
    - < 0.5:   QUARANTINED (Isolated in data/quarantine/, status QUARANTINED in SQLite)
"""

from __future__ import annotations

import json
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import structlog
from pydantic import BaseModel, Field

from app.infrastructure.ingestion.models.canonical_page import (
    CanonicalPage,
    IssueSeverityEnum,
    QualityIssue,
)
from app.infrastructure.ingestion.models.chunk_model import Chunk
from app.infrastructure.ingestion.quality.gates import (
    Gate1StructureValidator,
    Gate2ContentValidator,
    Gate3EntityValidator,
    Gate4ChunkValidator,
    Gate5CorpusValidator,
    GateResult,
)

logger = structlog.get_logger(__name__)


class QualityStatusEnum(str, Enum):
    """Quality approval status resulting from validation."""

    AUTO_APPROVED = "AUTO_APPROVED"
    APPROVED_WITH_WARNINGS = "APPROVED_WITH_WARNINGS"
    QUARANTINED = "QUARANTINED"


class ValidationReport(BaseModel):
    """Comprehensive validation report for a CanonicalPage or Chunk."""

    target_id: str = Field(..., description="Target identifier (page_id or chunk_id).")
    target_title: str = Field(..., description="Target title.")
    composite_score: float = Field(..., ge=0.0, le=1.0, description="Overall weighted quality score.")
    status: QualityStatusEnum = Field(..., description="Approval status: AUTO_APPROVED, WARNING, QUARANTINED.")
    gate_results: List[GateResult] = Field(default_factory=list, description="Per-gate validation results.")
    all_issues: List[QualityIssue] = Field(default_factory=list, description="All quality issues aggregated.")


class QualityValidator:
    """Main Quality Validation Engine managing 5-Gate checks & quarantine isolation."""

    def __init__(
        self,
        quarantine_dir: Path = Path("data/quarantine"),
        auto_approve_threshold: float = 0.8,
        quarantine_threshold: float = 0.5,
    ):
        """
        Initialize QualityValidator.

        Args:
            quarantine_dir: Path to directory where quarantined pages are saved.
            auto_approve_threshold: Threshold for AUTO_APPROVED status (default 0.8).
            quarantine_threshold: Threshold below which pages are QUARANTINED (default 0.5).
        """
        self.quarantine_dir = quarantine_dir
        self.auto_approve_threshold = auto_approve_threshold
        self.quarantine_threshold = quarantine_threshold

    def validate_canonical_page(self, page: CanonicalPage) -> ValidationReport:
        """
        Run Gates 1, 2, 3 validation on a CanonicalPage.

        Returns:
            ValidationReport with composite score and approval status.
        """
        # Run individual gates
        g1 = Gate1StructureValidator.validate(page)
        g2 = Gate2ContentValidator.validate(page)
        g3 = Gate3EntityValidator.validate(page)

        gate_results = [g1, g2, g3]

        # Calculate composite score (weighted average: G1 35%, G2 40%, G3 25%)
        composite = round(0.35 * g1.score + 0.40 * g2.score + 0.25 * g3.score, 2)

        # Aggregate all issues
        all_issues: List[QualityIssue] = []
        for g in gate_results:
            all_issues.extend(g.issues)
        all_issues.extend(page.quality.issues)

        # Critical severity check forces quarantine
        has_critical = any(i.severity == IssueSeverityEnum.CRITICAL for i in all_issues)

        if has_critical or composite < self.quarantine_threshold:
            status = QualityStatusEnum.QUARANTINED
        elif composite >= self.auto_approve_threshold:
            status = QualityStatusEnum.AUTO_APPROVED
        else:
            status = QualityStatusEnum.APPROVED_WITH_WARNINGS

        report = ValidationReport(
            target_id=str(page.identity.page_id),
            target_title=page.identity.title,
            composite_score=composite,
            status=status,
            gate_results=gate_results,
            all_issues=all_issues,
        )

        logger.info(
            "page_validated",
            page_id=page.identity.page_id,
            score=composite,
            status=status.value,
            issues_count=len(all_issues),
        )

        return report

    def validate_chunks(self, chunks: List[Chunk]) -> List[ValidationReport]:
        """
        Run Gate 4 validation across a list of Chunks.

        Returns:
            List of ValidationReports per chunk.
        """
        reports: List[ValidationReport] = []
        seen_hashes: Set[str] = set()

        for c in chunks:
            g4 = Gate4ChunkValidator.validate(c, seen_hashes)

            if g4.score >= self.auto_approve_threshold:
                status = QualityStatusEnum.AUTO_APPROVED
            elif g4.score >= self.quarantine_threshold:
                status = QualityStatusEnum.APPROVED_WITH_WARNINGS
            else:
                status = QualityStatusEnum.QUARANTINED

            reports.append(
                ValidationReport(
                    target_id=str(c.chunk_id),
                    target_title=f"{c.page_title} - Chunk {c.chunk_index}",
                    composite_score=g4.score,
                    status=status,
                    gate_results=[g4],
                    all_issues=g4.issues,
                )
            )

        return reports

    def quarantine_page(self, page: CanonicalPage, report: ValidationReport) -> Path:
        """
        Isolate a quarantined CanonicalPage to data/quarantine/.

        Returns:
            Path to the saved quarantine JSON file.
        """
        self.quarantine_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{page.identity.page_id}_{page.identity.canonical_slug}.quarantine.json"
        quarantine_path = self.quarantine_dir / filename

        quarantine_payload = {
            "page_id": page.identity.page_id,
            "title": page.identity.title,
            "canonical_slug": page.identity.canonical_slug,
            "composite_score": report.composite_score,
            "validation_report": report.model_dump(),
            "canonical_data": page.model_dump(),
        }

        quarantine_path.write_text(
            json.dumps(quarantine_payload, indent=2, default=str, ensure_ascii=False),
            encoding="utf-8",
        )

        logger.warning(
            "page_quarantined",
            page_id=page.identity.page_id,
            title=page.identity.title,
            score=report.composite_score,
            path=str(quarantine_path),
        )

        return quarantine_path

    def generate_corpus_report(
        self,
        pages: List[CanonicalPage],
        chunks: List[Chunk],
    ) -> Dict[str, Any]:
        """Generate Gate 5 Corpus Statistics report."""
        return Gate5CorpusValidator.validate_corpus(pages, chunks)
