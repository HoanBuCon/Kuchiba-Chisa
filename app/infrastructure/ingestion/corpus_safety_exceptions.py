"""Load strict curator exception manifests at an explicitly authorized boundary."""

from __future__ import annotations

from pathlib import Path

from app.domain.models.corpus_safety_exception import (
    CorpusSafetyExceptionManifest,
    PageSafetyExceptionManifest,
)


def load_corpus_safety_exception_manifest(
    path: Path,
) -> CorpusSafetyExceptionManifest:
    """Parse a version-controlled manifest without repairing malformed approvals."""

    return CorpusSafetyExceptionManifest.model_validate_json(path.read_text(encoding="utf-8"))


def load_page_safety_exceptions(path: Path) -> PageSafetyExceptionManifest:
    """Parse the owner's page approvals; a malformed file stops the run instead of exempting."""

    return PageSafetyExceptionManifest.model_validate_json(path.read_text(encoding="utf-8"))
