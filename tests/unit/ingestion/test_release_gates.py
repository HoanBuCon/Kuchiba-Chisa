"""Data gate: hard limits, quarantine ratio, safety and the change envelope."""

from copy import deepcopy

from app.domain.ingestion.release_gates import (
    RetrievalGatePolicy,
    evaluate_data_gate,
    evaluate_retrieval_gate,
)
from app.infrastructure.ingestion.gates_config import load_gate_policies

MANIFEST = {
    "quality": {
        "chunks": 1000,
        "pages": 100,
        "over_limit": 0,
        "duplicate_bodies": 0,
        "uncovered_units": 0,
        "pages_quarantined": 1,
        "pages_safety_blocked": 0,
    },
    "counts": {
        "collection": {"lore_canon": 700, "lore_dialogue": 300},
        "knowledge": {"entities": 100, "aliases": 400},
    },
}


def _changed(**quality) -> dict:
    manifest = deepcopy(MANIFEST)
    manifest["quality"].update(quality)
    return manifest


def test_clean_first_release_passes() -> None:
    report = evaluate_data_gate(MANIFEST)

    assert report.passed and report.failures == ()


def test_each_hard_limit_fails_on_its_own() -> None:
    for field, name in (
        ("over_limit", "chunks_over_token_limit"),
        ("duplicate_bodies", "duplicate_chunk_bodies"),
        ("uncovered_units", "uncovered_units"),
        ("pages_safety_blocked", "unresolved_safety_pages"),
    ):
        assert evaluate_data_gate(_changed(**{field: 1})).failures == (name,)


def test_quarantine_above_two_percent_fails() -> None:
    assert evaluate_data_gate(_changed(pages_quarantined=2)).passed
    assert evaluate_data_gate(_changed(pages_quarantined=3)).failures == (
        "pages_quarantined_ratio",
    )


def test_empty_collection_fails() -> None:
    manifest = deepcopy(MANIFEST)
    manifest["counts"]["collection"]["lore_dialogue"] = 0

    assert evaluate_data_gate(manifest).failures == ("collection_not_empty:lore_dialogue",)


def test_change_envelope_compares_with_the_active_release() -> None:
    assert evaluate_data_gate(_changed(chunks=1100), MANIFEST).passed
    assert evaluate_data_gate(_changed(chunks=1101), MANIFEST).failures == ("chunk_change:chunks",)

    shrunk = deepcopy(MANIFEST)
    shrunk["counts"]["knowledge"]["aliases"] = 379
    assert evaluate_data_gate(shrunk, MANIFEST).failures == ("knowledge_change:aliases",)


def test_manifest_that_never_measured_safety_fails() -> None:
    manifest = deepcopy(MANIFEST)
    del manifest["quality"]["pages_safety_blocked"]

    assert evaluate_data_gate(manifest).failures == ("manifest_complete",)


SUMMARY = {
    "verified_cases": 100,
    "overall": {"cases": 100, "hit_at_5": 0.95, "hit_at_5_ci95": [0.9, 0.98], "mrr_at_10": 0.85},
}
RETRIEVAL = RetrievalGatePolicy(canary_case_ids=("a", "b"))


def _summary(**overall) -> dict:
    return {"verified_cases": 100, "overall": SUMMARY["overall"] | overall}


def _retrieval_failures(summary: dict, hits=("a", "b"), active=None) -> tuple[str, ...]:
    return evaluate_retrieval_gate(summary, hits, active, RETRIEVAL).failures


def test_retrieval_gate_passes_at_the_targets() -> None:
    assert _retrieval_failures(SUMMARY) == ()


def test_retrieval_gate_fails_on_each_target() -> None:
    assert _retrieval_failures(SUMMARY | {"verified_cases": 99}) == ("golden_verified_cases",)
    assert _retrieval_failures(_summary(hit_at_5=0.89)) == ("hit_at_5",)
    assert _retrieval_failures(_summary(mrr_at_10=0.79)) == ("mrr_at_10",)


def test_one_missed_canary_fails_the_gate() -> None:
    assert _retrieval_failures(SUMMARY, hits=("a",)) == ("canary",)


def test_empty_canary_list_cannot_pass() -> None:
    report = evaluate_retrieval_gate(SUMMARY, (), None, RetrievalGatePolicy())

    assert report.failures == ("canary_configured",)


def test_drop_from_active_counts_only_beyond_the_interval() -> None:
    active = _summary(hit_at_5=0.97, mrr_at_10=0.85)
    assert _retrieval_failures(SUMMARY, active=active) == ()

    noisy_free = _summary(hit_at_5=0.95, hit_at_5_ci95=[0.9, 0.96])
    assert _retrieval_failures(noisy_free, active=active) == ("hit_at_5_vs_active",)
    assert _retrieval_failures(_summary(mrr_at_10=0.82), active=active) == ("mrr_at_10_vs_active",)


def test_shipped_gate_config_loads_with_canaries() -> None:
    data, retrieval = load_gate_policies()

    assert data.max_quarantined_ratio == 0.02
    assert (retrieval.min_hit_at_5, retrieval.min_mrr_at_10) == (0.90, 0.80)
    assert len(retrieval.canary_case_ids) >= 10
