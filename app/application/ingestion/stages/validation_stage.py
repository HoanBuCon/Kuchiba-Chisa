"""Canonical chunk validation before embedding or staging."""

from __future__ import annotations

import time
import uuid

from pydantic import BaseModel

from app.domain.entities.chunk_models import ProcessingChunk
from app.domain.interfaces.pipeline import IPipelineStage, PipelineMetrics, PipelineResult
from app.domain.interfaces.repositories import IPipelineJobRepository
from app.domain.models.corpus_safety_exception import CorpusSafetyProvenance
from app.domain.services.guardrails import CorpusSafetyGate
from app.domain.services.guardrails.pii_redaction import PiiRedactor
from app.shared.utils.logger import get_logger

log = get_logger(__name__)


class ValidationInput(BaseModel):
    chunks: list[ProcessingChunk]


class ValidationStage(IPipelineStage[ValidationInput, list[ProcessingChunk]]):
    """Reject invalid or sensitive canonical chunks before provider/storage boundaries."""

    def __init__(
        self,
        job_repo: IPipelineJobRepository,
        pii_detector: PiiRedactor | None = None,
        corpus_safety_gate: CorpusSafetyGate | None = None,
    ) -> None:
        self.job_repo = job_repo
        self._pii_detector = pii_detector or PiiRedactor()
        self._corpus_safety_gate = corpus_safety_gate or CorpusSafetyGate()

    async def execute(
        self,
        job_id: uuid.UUID,
        input_data: ValidationInput,
    ) -> PipelineResult[list[ProcessingChunk]]:
        log.info("Starting ValidationStage", job_id=job_id, chunks=len(input_data.chunks))
        start_time = time.perf_counter()
        items_failed = 0

        for chunk in input_data.chunks:
            chunk.is_valid = True
            chunk.validation_errors = []

            content_len = len(chunk.text_content)
            if content_len < 10:
                chunk.is_valid = False
                chunk.validation_errors.append("Chunk is too short (< 10 chars)")
            elif content_len > 4_000:
                chunk.is_valid = False
                chunk.validation_errors.append(f"Chunk is oversized ({content_len} chars)")

            if not chunk.payload:
                chunk.is_valid = False
                chunk.validation_errors.append("Missing LorePayload")

            pii_result = self._pii_detector.redact(chunk.text_content)
            if pii_result.changed:
                chunk.is_valid = False
                categories = ",".join(sorted(pii_result.categories))
                chunk.validation_errors.append(f"Sensitive data detected ({categories})")

            safety = self._corpus_safety_gate.inspect(
                text=chunk.text_content,
                source_id=f"page:{chunk.page_id}:chunk:{chunk.chunk_id}",
                checksum=chunk.chunk_hash,
                provenance=(
                    CorpusSafetyProvenance(
                        source_id=str(chunk.source_id),
                        corpus_version=chunk.corpus_version,
                        page_id=chunk.page_id,
                        revision_id=chunk.revision_id,
                        chunk_id=str(chunk.chunk_id),
                    )
                    if chunk.source_id is not None
                    and chunk.corpus_version is not None
                    else None
                ),
            )
            if safety.quarantined:
                chunk.is_valid = False
                chunk.validation_errors.append(
                    f"Corpus safety gate quarantined ({safety.rule_id})"
                )
            elif safety.exception_applied:
                await self.job_repo.log_event(
                    job_id,
                    "CorpusSafetyExceptionValidated",
                    {
                        "source_id": safety.source_id,
                        "checksum": safety.checksum,
                        "rule_id": safety.rule_id,
                        "finding_fingerprint": safety.fingerprint,
                        "exception_id": safety.exception_id,
                        "curator_reason": safety.exception_reason,
                        "approved_by": safety.approved_by,
                        "approved_at": safety.approved_at,
                        "provenance": (
                            safety.provenance.model_dump(mode="json")
                            if safety.provenance is not None
                            else None
                        ),
                    },
                )

            if "|" in chunk.text_content and "-|-" in chunk.text_content:
                lines = chunk.text_content.splitlines()
                table_lines = [line for line in lines if "|" in line]
                if len(table_lines) == 1:
                    chunk.is_valid = False
                    chunk.validation_errors.append("Potentially broken markdown table")

            if not chunk.is_valid:
                log.warning(
                    "Chunk validation failed",
                    chunk_id=chunk.chunk_id,
                    errors=chunk.validation_errors,
                )
                items_failed += 1

        valid_chunks = [chunk for chunk in input_data.chunks if chunk.is_valid]
        metrics = PipelineMetrics(
            duration_seconds=time.perf_counter() - start_time,
            items_processed=len(input_data.chunks),
            items_failed=items_failed,
            items_skipped=0,
        )

        await self.job_repo.log_event(job_id, "ValidationComplete", metrics.model_dump())
        return PipelineResult(output=valid_chunks, metrics=metrics)
