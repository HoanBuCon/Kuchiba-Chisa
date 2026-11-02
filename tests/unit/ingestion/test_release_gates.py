"""Data gate: hard limits, quarantine ratio, safety and the change envelope."""

from copy import deepcopy

from app.domain.ingestion.release_gates import evaluate_data_gate

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
