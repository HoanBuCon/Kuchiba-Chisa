"""Load strict curator exception manifests at an explicitly authorized boundary."""

from __future__ import annotations

from pathlib import Path

from app.domain.models.corpus_safety_exception import CorpusSafetyExceptionManifest


def load_corpus_safety_exception_manifest(
    path: Path,
) -> CorpusSafetyExceptionManifest:
    """Parse a version-controlled manifest without repairing malformed approvals."""

    return CorpusSafetyExceptionManifest.model_validate_json(path.read_text(encoding="utf-8"))
