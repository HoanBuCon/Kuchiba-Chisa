"""Focused regression tests for the auditable Ruff debt ratchet."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType


def _load_script() -> ModuleType:
    path = Path("scripts/ruff_debt_ratchet.py")
    spec = importlib.util.spec_from_file_location("ruff_debt_ratchet", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _finding(code: str, filename: str = "app/domain/example.py") -> dict[str, object]:
    return {"code": code, "filename": filename}


def _baseline(total: int) -> dict[str, object]:
    return {
        "schema_version": "ruff-debt-baseline-v1",
        "audit": {"total": total},
    }


def test_ratchet_accepts_equal_or_reduced_style_debt() -> None:
    module = _load_script()
    audit = module.summarize([_finding("E501"), _finding("I001")], Path.cwd())

    assert module.evaluate(audit, _baseline(2)) == []
    assert module.evaluate(audit, _baseline(3)) == []


def test_ratchet_rejects_increased_debt() -> None:
    module = _load_script()
    audit = module.summarize([_finding("E501"), _finding("E501")], Path.cwd())

    assert module.evaluate(audit, _baseline(1)) == [
        "Ruff debt increased: current=2 baseline=1"
    ]


def test_semantic_finding_blocks_even_below_aggregate_baseline() -> None:
    module = _load_script()
    audit = module.summarize([_finding("F821")], Path.cwd())

    errors = module.evaluate(audit, _baseline(100))

    assert len(errors) == 1
    assert "F821" in errors[0]


def test_summary_is_auditable_by_rule_file_and_module() -> None:
    module = _load_script()
    audit = module.summarize(
        [
            _finding("E501", "app/domain/a.py"),
            _finding("E501", "app/domain/a.py"),
            _finding("I001", "tests/unit/test_a.py"),
        ],
        Path.cwd(),
    )

    assert audit == {
        "total": 3,
        "by_rule": {"E501": 2, "I001": 1},
        "by_file": {"app/domain/a.py": 2, "tests/unit/test_a.py": 1},
        "by_module": {"app/domain": 2, "tests/unit": 1},
        "blocking_rules": {},
    }
