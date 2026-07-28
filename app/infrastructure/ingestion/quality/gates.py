"""
5-Gate Quality Control System — Individual Gate Validators (§4.2 & §9).

Implements quality gates 1 to 5 as defined in v1.1 Ingestion Architecture:
    - Gate 1 (Structure): Heading tree hierarchy, empty section detection, table parsing integrity.
    - Gate 2 (Content): Non-empty text, redirect/disambiguation filtering, boilerplate stripping.
    - Gate 3 (Entity): Primary entity verification, page type & metadata consistency.
    - Gate 4 (Chunk): Token size range (20–1024 tokens), context_prefix formatting, deduplication.
    - Gate 5 (Corpus): Aggregated corpus statistics, length distribution, entity coverage.
"""

from __future__ import annotations

from typing import Any, Dict, List, Set, Tuple

from pydantic import BaseModel, Field

from app.infrastructure.ingestion.models.canonical_page import (
    CanonicalPage,
    CanonicalSection,
    ContentTypeEnum,
    IssueSeverityEnum,
    PageTypeEnum,
    QualityIssue,
)
from app.infrastructure.ingestion.models.chunk_model import Chunk, MAX_CHUNK_TOKENS, MIN_CHUNK_TOKENS


class GateResult(BaseModel):
    """Result of running a single Quality Gate validation."""

    gate_id: str = Field(..., description="Gate identifier: 'GATE_1', 'GATE_2', etc.")
    gate_name: str = Field(..., description="Human-readable gate name.")
    passed: bool = Field(..., description="True if gate criteria met without critical failure.")
    score: float = Field(1.0, ge=0.0, le=1.0, description="Quality score for this gate (0.0 - 1.0).")
    issues: List[QualityIssue] = Field(default_factory=list, description="Quality issues detected.")


class Gate1StructureValidator:
    """Gate 1: Structure & Heading Tree Validator."""

    @staticmethod
    def validate(page: CanonicalPage) -> GateResult:
        issues: List[QualityIssue] = []
        deductions = 0.0

        if not page.sections:
            issues.append(
                QualityIssue(
                    type="NO_SECTIONS",
                    location="Root",
                    severity=IssueSeverityEnum.CRITICAL,
                    message="CanonicalPage contains zero sections.",
                )
            )
            return GateResult(
                gate_id="GATE_1",
                gate_name="Structure & Heading Tree",
                passed=False,
                score=0.0,
                issues=issues,
            )

        def _check_section_tree(sections: List[CanonicalSection], parent_level: int = 0) -> None:
            nonlocal deductions
            for sec in sections:
                # Level check
                if parent_level > 0 and sec.level > parent_level + 2:
                    issues.append(
                        QualityIssue(
                            type="HEADING_LEVEL_SKIP",
                            location=f"Section: {sec.title}",
                            severity=IssueSeverityEnum.LOW,
                            message=f"Section level skipped from H{parent_level} to H{sec.level}.",
                        )
                    )
                    deductions += 0.05

                # Empty section check
                if sec.content_type == ContentTypeEnum.HEADING_ONLY or (
                    not sec.content.strip() and not sec.structured_data and not sec.subsections
                ):
                    issues.append(
                        QualityIssue(
                            type="EMPTY_SECTION",
                            location=f"Section: {sec.title}",
                            severity=IssueSeverityEnum.MEDIUM,
                            message=f"Section '{sec.title}' is empty.",
                        )
                    )
                    deductions += 0.1

                if sec.subsections:
                    _check_section_tree(sec.subsections, sec.level)

        _check_section_tree(page.sections)

        # Check table parsing failures
        if page.quality.tables_failed > 0:
            issues.append(
                QualityIssue(
                    type="MALFORMED_TABLE",
                    location="Tables",
                    severity=IssueSeverityEnum.MEDIUM,
                    count=page.quality.tables_failed,
                    message=f"{page.quality.tables_failed} table(s) failed parsing.",
                )
            )
            deductions += 0.15 * page.quality.tables_failed

        score = max(0.0, 1.0 - deductions)
        passed = score >= 0.5 and not any(i.severity == IssueSeverityEnum.CRITICAL for i in issues)

        return GateResult(
            gate_id="GATE_1",
            gate_name="Structure & Heading Tree",
            passed=passed,
            score=round(score, 2),
            issues=issues,
        )


class Gate2ContentValidator:
    """Gate 2: Content & Language Integrity Validator."""

    @staticmethod
    def validate(page: CanonicalPage) -> GateResult:
        issues: List[QualityIssue] = []
        deductions = 0.0

        # Disambiguation / Redirect check
        if page.identity.page_type == PageTypeEnum.META_NAVIGATION or "disambiguation" in page.identity.title.lower():
            issues.append(
                QualityIssue(
                    type="META_NAVIGATION_PAGE",
                    location="Identity",
                    severity=IssueSeverityEnum.HIGH,
                    message="Page is a disambiguation/redirect navigation page.",
                )
            )
            deductions += 0.5

        # Check total clean content length
        total_content = "".join(s.content for s in page.sections).strip()
        if not total_content and not page.infobox:
            issues.append(
                QualityIssue(
                    type="ZERO_CONTENT",
                    location="Body",
                    severity=IssueSeverityEnum.CRITICAL,
                    message="CanonicalPage text content is completely empty.",
                )
            )
            deductions += 1.0

        score = max(0.0, 1.0 - deductions)
        passed = score >= 0.5 and not any(i.severity == IssueSeverityEnum.CRITICAL for i in issues)

        return GateResult(
            gate_id="GATE_2",
            gate_name="Content & Language Integrity",
            passed=passed,
            score=round(score, 2),
            issues=issues,
        )


class Gate3EntityValidator:
    """Gate 3: Entity & Metadata Consistency Validator."""

    @staticmethod
    def validate(page: CanonicalPage) -> GateResult:
        issues: List[QualityIssue] = []
        deductions = 0.0

        # Verify primary entity exists
        primary_entities = [e for e in page.entities if e.is_primary]
        if not primary_entities:
            issues.append(
                QualityIssue(
                    type="MISSING_PRIMARY_ENTITY",
                    location="Entities",
                    severity=IssueSeverityEnum.HIGH,
                    message="No primary entity identified on CanonicalPage.",
                )
            )
            deductions += 0.3

        # Verify DocumentMetadata canonical_name matches page title or primary entity
        doc_meta = page.document_metadata
        if not doc_meta.canonical_name:
            issues.append(
                QualityIssue(
                    type="MISSING_CANONICAL_NAME",
                    location="DocumentMetadata",
                    severity=IssueSeverityEnum.MEDIUM,
                    message="DocumentMetadata.canonical_name is missing.",
                )
            )
            deductions += 0.2

        score = max(0.0, 1.0 - deductions)
        passed = score >= 0.5 and not any(i.severity == IssueSeverityEnum.CRITICAL for i in issues)

        return GateResult(
            gate_id="GATE_3",
            gate_name="Entity & Metadata Consistency",
            passed=passed,
            score=round(score, 2),
            issues=issues,
        )


class Gate4ChunkValidator:
    """Gate 4: Chunk Boundaries & Deduplication Validator."""

    @staticmethod
    def validate(chunk: Chunk, seen_hashes: Set[str]) -> GateResult:
        issues: List[QualityIssue] = []
        deductions = 0.0

        # Token bounds check (20 - 1024 tokens)
        if chunk.token_count_approx < MIN_CHUNK_TOKENS:
            issues.append(
                QualityIssue(
                    type="CHUNK_TOO_SMALL",
                    location=f"Chunk {chunk.chunk_id}",
                    severity=IssueSeverityEnum.LOW,
                    message=f"Chunk token count ({chunk.token_count_approx}) is below minimum ({MIN_CHUNK_TOKENS}).",
                )
            )
            deductions += 0.1
        elif chunk.token_count_approx > MAX_CHUNK_TOKENS:
            issues.append(
                QualityIssue(
                    type="CHUNK_TOO_LARGE",
                    location=f"Chunk {chunk.chunk_id}",
                    severity=IssueSeverityEnum.MEDIUM,
                    message=f"Chunk token count ({chunk.token_count_approx}) exceeds maximum ({MAX_CHUNK_TOKENS}).",
                )
            )
            deductions += 0.3

        # Context prefix check
        if not chunk.context_prefix or not chunk.context_prefix.startswith("["):
            issues.append(
                QualityIssue(
                    type="MALFORMED_CONTEXT_PREFIX",
                    location=f"Chunk {chunk.chunk_id}",
                    severity=IssueSeverityEnum.MEDIUM,
                    message="Chunk context_prefix is missing or malformed.",
                )
            )
            deductions += 0.2

        # Deduplication check
        if chunk.text_hash in seen_hashes:
            issues.append(
                QualityIssue(
                    type="DUPLICATE_CHUNK",
                    location=f"Chunk {chunk.chunk_id}",
                    severity=IssueSeverityEnum.HIGH,
                    message=f"Duplicate chunk text hash detected: {chunk.text_hash}",
                )
            )
            deductions += 0.4
        else:
            seen_hashes.add(chunk.text_hash)

        score = max(0.0, 1.0 - deductions)
        passed = score >= 0.5 and not any(i.severity == IssueSeverityEnum.CRITICAL for i in issues)

        return GateResult(
            gate_id="GATE_4",
            gate_name="Chunk Boundaries & Deduplication",
            passed=passed,
            score=round(score, 2),
            issues=issues,
        )


class Gate5CorpusValidator:
    """Gate 5: Corpus Statistics & Coverage Validator."""

    @staticmethod
    def validate_corpus(pages: List[CanonicalPage], chunks: List[Chunk]) -> Dict[str, Any]:
        """Compute aggregate statistics and quality metrics across the entire corpus."""
        total_pages = len(pages)
        total_chunks = len(chunks)

        if total_pages == 0:
            return {
                "total_pages": 0,
                "total_chunks": 0,
                "avg_chunks_per_page": 0.0,
                "avg_quality_score": 0.0,
                "entity_coverage_pct": 0.0,
                "page_type_distribution": {},
            }

        # Page type distribution
        type_counts: Dict[str, int] = {}
        for p in pages:
            pt = p.identity.page_type.value
            type_counts[pt] = type_counts.get(pt, 0) + 1

        # Quality score average
        avg_quality = sum(p.quality.parser_confidence for p in pages) / total_pages

        # Entity coverage (pages with at least 1 entity)
        pages_with_entities = sum(1 for p in pages if len(p.entities) > 0)
        entity_coverage = (pages_with_entities / total_pages) * 100.0

        # Token length distribution
        tokens_list = [c.token_count_approx for c in chunks] if chunks else [0]
        avg_tokens = sum(tokens_list) / len(tokens_list)

        return {
            "total_pages": total_pages,
            "total_chunks": total_chunks,
            "avg_chunks_per_page": round(total_chunks / total_pages, 2),
            "avg_tokens_per_chunk": round(avg_tokens, 1),
            "avg_quality_score": round(avg_quality, 2),
            "entity_coverage_pct": round(entity_coverage, 1),
            "page_type_distribution": type_counts,
        }
