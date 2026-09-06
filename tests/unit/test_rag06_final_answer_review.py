"""Structural regressions for the human-gated RAG-06 review artifact."""

from __future__ import annotations

import copy
import json

from scripts.prepare_rag06_final_answer_review import (
    ANSWERABLE_SAMPLE_SIZE,
    GOLDEN_SET,
    JINA_ARTIFACT,
    select_review_cases,
    validate_review_artifact,
)
from scripts.validate_rag05_raw_wiki_golden import _content_fingerprint


def _pending_artifact() -> tuple[dict, dict, dict]:
    golden = json.loads(GOLDEN_SET.read_text(encoding="utf-8"))
    jina = json.loads(JINA_ARTIFACT.read_text(encoding="utf-8"))
    fingerprint = _content_fingerprint(golden)
    selected = select_review_cases(
        golden["cases"], dataset_fingerprint=fingerprint
    )
    jina_by_id = {item["case_id"]: item for item in jina["case_results"]}
    cases = []
    for source in selected:
        ranked = jina_by_id[source["id"]]["reranked_top_k_evidence_ids"][:5]
        cases.append(
            {
                "case_id": source["id"],
                "query": source["query"],
                "expected_behavior": (
                    "answer" if source["expected_behavior"] == "retrieve" else "abstain"
                ),
                "selected_evidence": [
                    {"evidence_id": evidence_id} for evidence_id in ranked
                ],
                "generation": {
                    "candidate_redacted_for_prompt_leakage": False,
                    "candidate_answer": None,
                    "input_tokens": 1,
                },
                "human_review": {"status": "pending", "reviewed_by": None},
            }
        )
    artifact = {
        "provenance": {
            "approved_content_sha256": fingerprint,
            "staging_version": jina["staging_version"],
        },
        "cases": cases,
    }
    return artifact, golden, jina


def test_stratified_sample_is_deterministic_and_includes_all_abstentions() -> None:
    golden = json.loads(GOLDEN_SET.read_text(encoding="utf-8"))
    fingerprint = _content_fingerprint(golden)

    first = select_review_cases(golden["cases"], dataset_fingerprint=fingerprint)
    second = select_review_cases(golden["cases"], dataset_fingerprint=fingerprint)

    assert [case["id"] for case in first] == [case["id"] for case in second]
    assert sum(case["expected_behavior"] == "retrieve" for case in first) == (
        ANSWERABLE_SAMPLE_SIZE
    )
    assert {
        case["id"] for case in first if case["expected_behavior"] == "abstain"
    } == {"rw-082", "rw-083"}


def test_structural_validator_accepts_only_pending_human_semantics() -> None:
    artifact, golden, jina = _pending_artifact()

    valid = validate_review_artifact(artifact, golden=golden, jina=jina)
    assert valid["status"] == "PASS"
    assert valid["answerable_cases"] == ANSWERABLE_SAMPLE_SIZE
    assert valid["abstention_cases"] == 2

    auto_approved = copy.deepcopy(artifact)
    auto_approved["cases"][0]["human_review"] = {
        "status": "approved",
        "reviewed_by": "automation",
    }
    invalid = validate_review_artifact(auto_approved, golden=golden, jina=jina)
    assert invalid["status"] == "FAIL"
    assert "semantic review was auto-approved" in invalid["errors"][0]


def test_structural_validator_rejects_rank_evidence_drift() -> None:
    artifact, golden, jina = _pending_artifact()
    artifact["cases"][0]["selected_evidence"][0]["evidence_id"] = "tampered"

    validation = validate_review_artifact(artifact, golden=golden, jina=jina)

    assert validation["status"] == "FAIL"
    assert any("rank/evidence mismatch" in error for error in validation["errors"])
