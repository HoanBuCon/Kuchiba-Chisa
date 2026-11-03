"""Load the release gate thresholds (`app/config/ingestion/gates.yaml`)."""

from __future__ import annotations

from pathlib import Path

import yaml

from app.domain.ingestion.release_gates import DataGatePolicy, RetrievalGatePolicy
from app.infrastructure.ingestion.silver.rules import CONFIG_DIR


def load_gate_policies(
    path: Path = CONFIG_DIR / "gates.yaml",
) -> tuple[DataGatePolicy, RetrievalGatePolicy]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    retrieval = dict(raw["retrieval"])
    retrieval["canary_case_ids"] = tuple(retrieval["canary_case_ids"])
    return DataGatePolicy(**raw["data"]), RetrievalGatePolicy(**retrieval)
