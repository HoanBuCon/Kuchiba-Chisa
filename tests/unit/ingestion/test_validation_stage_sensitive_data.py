"""ING-03 canonical PII/secret scanning before embedding and staging."""

from __future__ import annotations

import hashlib
import uuid

import pytest

from app.application.ingestion.stages.validation_stage import ValidationInput, ValidationStage
from app.domain.entities.chunk_models import ProcessingChunk
from app.domain.entities.lore import LorePayload


class _JobRepository:
    def __init__(self) -> None:
        self.events: list[tuple[uuid.UUID, str, dict[str, object]]] = []

    async def log_event(
        self,
        job_id: uuid.UUID,
        event_type: str,
        details: dict[str, object],
    ) -> None:
        self.events.append((job_id, event_type, details))


def _chunk(text: str) -> ProcessingChunk:
    parent_id = uuid.uuid4()
    chunk_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return ProcessingChunk(
        parent_id=parent_id,
        page_id=42,
        revision_id=7,
        page_title="Reviewed lore",
        chunk_index=0,
        text_content=text,
        chunk_hash=chunk_hash,
        payload=LorePayload(
            parent_id=str(parent_id),
            page_id=42,
            source_file="reviewed.wikitext",
            revision_id=7,
            text_content=text,
            chunk_hash=chunk_hash,
        ),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("text", "category"),
    [
        ("Contact the curator at lore.owner@example.com for access.", "email"),
        ("Provider credential api_key=abcdefghijklmnop must never be indexed.", "secret"),
        ("Private contact number is +84 912 345 678 and must be quarantined.", "phone"),
    ],
)
async def test_sensitive_chunk_is_rejected_with_category_only_audit(
    text: str,
    category: str,
) -> None:
    repository = _JobRepository()
    chunk = _chunk(text)

    result = await ValidationStage(repository).execute(
        uuid.uuid4(), ValidationInput(chunks=[chunk])
    )

    assert result.output == []
    assert result.metrics.items_failed == 1
    assert chunk.validation_errors == [f"Sensitive data detected ({category})"]
    audit_text = str(repository.events)
    assert text not in audit_text
    assert "abcdefghijklmnop" not in audit_text


@pytest.mark.asyncio
async def test_benign_lore_passes_without_sensitive_data_false_positive() -> None:
    repository = _JobRepository()
    chunk = _chunk("Aalto is a Consultant of the Black Shores.")

    result = await ValidationStage(repository).execute(
        uuid.uuid4(), ValidationInput(chunks=[chunk])
    )

    assert result.output == [chunk]
    assert result.metrics.items_failed == 0
    assert chunk.validation_errors == []
