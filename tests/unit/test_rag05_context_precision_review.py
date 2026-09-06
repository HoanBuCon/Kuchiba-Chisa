"""Contracts for RAG-05 top-k context-precision annotation review."""

from __future__ import annotations

import copy

from scripts.prepare_rag05_context_precision_review import (
    NOT_EVALUABLE,
    build_review_dataset,
    record_human_approval,
    validate_review_dataset,
)


def test_real_review_draft_preserves_rank_evidence_and_excludes_abstentions() -> None:
    review = build_review_dataset()
    validation = validate_review_dataset(review)

    assert validation["result"] == "PASS_PENDING_HUMAN_REVIEW"
    assert validation["answerable_cases"] == 81
    assert validation["abstention_cases_excluded"] == 2
    assert validation["annotation_items"] == 405
    assert validation["invalid_evidence_ids"] == []
    assert validation["rank_evidence_mismatches"] == []
    assert validation["duplicate_annotation_ids"] == []
    assert validation["abstention_annotations"] == []
    assert validation["golden_set_fingerprint_unchanged"] is True
    assert validation["jina_artifact_fingerprint_unchanged"] is True


def test_pending_and_ambiguous_labels_are_never_counted_as_irrelevant() -> None:
    review = build_review_dataset()
    review["annotations"][0]["human_review"]["label"] = "ambiguous"

    validation = validate_review_dataset(review)

    assert validation["human_label_counts"]["ambiguous"] == 1
    assert validation["human_label_counts"]["irrelevant"] == 0
    assert validation["pending_or_ambiguous_counted_as_irrelevant"] == 0
    assert validation["context_precision"] == NOT_EVALUABLE
    assert validation["srs_comparison"] == "NOT_EVALUABLE"


def test_duplicate_annotation_and_rank_mutation_fail_validation() -> None:
    review = build_review_dataset()
    duplicate = copy.deepcopy(review["annotations"][0])
    review["annotations"].append(duplicate)
    review["annotations"][1]["evidence_id"] = "raw_wiki:1:1:0000000000000000:chunk:000"

    validation = validate_review_dataset(review)

    assert validation["result"] == "FAIL"
    assert validation["duplicate_annotation_ids"]
    assert validation["invalid_evidence_ids"]
    assert validation["rank_evidence_mismatches"]


def test_approved_complete_binary_labels_produce_precision() -> None:
    review = build_review_dataset()
    review["approval"] = {
        "status": "approved",
        "approved_by": "human-reviewer",
        "approved_at": "2026-09-06T00:00:00Z",
    }
    for index, annotation in enumerate(review["annotations"]):
        annotation["human_review"]["label"] = (
            "relevant" if index % 4 else "irrelevant"
        )
        annotation["human_review"]["reviewed_by"] = "human-reviewer"
        annotation["human_review"]["reviewed_at"] = "2026-09-06T00:00:00Z"

    validation = validate_review_dataset(review)

    assert validation["evaluated_items"] == 405
    assert validation["human_label_counts"]["relevant"] == 303
    assert validation["human_label_counts"]["irrelevant"] == 102
    assert validation["context_precision"] == 0.748148
    assert validation["srs_comparison"] == "FAIL"


def test_explicit_all_relevant_human_approval_is_auditable_and_passes() -> None:
    review = record_human_approval(
        build_review_dataset(),
        reviewer="HoanBuCon",
        reviewed_at="2026-09-06T12:00:00+07:00",
        review_note="Human reviewed every item; source formatting noise remains.",
    )

    validation = validate_review_dataset(review)

    assert validation["result"] == "PASS"
    assert validation["evaluated_items"] == 405
    assert validation["human_label_counts"] == {
        "relevant": 405,
        "irrelevant": 0,
        "ambiguous": 0,
        "pending": 0,
    }
    assert validation["context_precision"] == 1.0
    assert validation["srs_comparison"] == "PASS"
