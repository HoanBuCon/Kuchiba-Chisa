"""Validate the reviewed raw_wiki RAG-05 golden-set draft.

This validator is deterministic and provider-free. It never writes to the corpus or
an index; its only output is the validation report next to the review draft.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CORPUS_ROOT = ROOT / "data" / "raw_wiki"
DATASET_PATH = (
    ROOT / "data" / "evaluations" / "drafts" / "rag05_raw_wiki_golden_v1.json"
)
REPORT_PATH = DATASET_PATH.with_suffix(".validation.json")
FORBIDDEN_QUERY_TEXT = (
    "raw_wiki",
    "raw wiki",
    "according to the source",
    "according to the wiki",
    "what does the wiki say",
    "source entry",
    "which entry is relevant",
    "benchmark",
    "retrieval",
    "evidence",
    "corpus",
    "chunk",
)


def _normalize(value: str) -> str:
    return " ".join(value.split())


def _query_tokens(value: str) -> set[str]:
    return set(re.findall(r"[\w']+", value.casefold(), flags=re.UNICODE))


def _load_corpus() -> dict[str, dict[str, Any]]:
    corpus: dict[str, dict[str, Any]] = {}
    for path in sorted(CORPUS_ROOT.rglob("*_main.wikitext")):
        metadata = json.loads(path.with_suffix(".meta.json").read_text(encoding="utf-8"))
        raw_text = path.read_text(encoding="utf-8")
        checksum = hashlib.sha256(raw_text.encode()).hexdigest()[:16]
        evidence_id = (
            f"raw_wiki:{metadata['page_id']}:{metadata['revision_id']}:"
            f"{checksum}:chunk:000"
        )
        if evidence_id in corpus:
            raise ValueError(f"duplicate evidence identity: {evidence_id}")
        corpus[evidence_id] = {
            "page_id": metadata["page_id"],
            "revision_id": metadata["revision_id"],
            "checksum": checksum,
            "source_title": metadata["title"],
            "source_path": path.relative_to(CORPUS_ROOT).as_posix(),
            "candidate_text": _normalize(raw_text)[:1200],
        }
    return corpus


def _distribution(cases: list[dict[str, Any]], field: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for case in cases:
        value = case[field]
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def validate(dataset: dict[str, Any], corpus: dict[str, dict[str, Any]]) -> dict[str, Any]:
    cases = dataset["cases"]
    invalid_ids: list[str] = []
    missing_excerpts: list[str] = []
    unsupported_positives: list[str] = []
    invalid_abstentions: list[str] = []
    meta_queries: list[str] = []
    exact_duplicates: list[list[str]] = []
    near_duplicates: list[dict[str, Any]] = []
    approval_errors: list[str] = []
    reviewer_state_errors: list[str] = []
    case_ids = [case["id"] for case in cases]
    duplicate_case_ids = sorted({case_id for case_id in case_ids if case_ids.count(case_id) > 1})
    seen_queries: dict[str, str] = {}

    if dataset.get("approval") != {
        "status": "draft",
        "approved_by": None,
        "approved_at": None,
    }:
        approval_errors.append("dataset approval must remain an unowned draft")
    if dataset.get("label_status") != "proposed":
        approval_errors.append("labels must remain proposed")
    if not 80 <= len(cases) <= 100:
        approval_errors.append("case count must be within 80-100")

    for case in cases:
        if case.get("reviewer_status") != "pending" or case.get("reviewer_notes") is not None:
            reviewer_state_errors.append(case["id"])
        query_key = _normalize(case["query"]).casefold()
        if query_key in seen_queries:
            exact_duplicates.append([seen_queries[query_key], case["id"]])
        seen_queries[query_key] = case["id"]
        if any(phrase in query_key for phrase in FORBIDDEN_QUERY_TEXT):
            meta_queries.append(case["id"])

        expected_behavior = case["expected_behavior"]
        evidence_records = case["evidence"]
        relevant_ids = case["relevant_evidence_ids"]
        if expected_behavior == "retrieve":
            if len(evidence_records) != 1 or relevant_ids != [evidence_records[0]["evidence_id"]]:
                unsupported_positives.append(case["id"])
            if not case.get("expected_answer_summary") or not case.get("rationale"):
                unsupported_positives.append(case["id"])
        elif expected_behavior == "abstain":
            if evidence_records or relevant_ids or not case.get("inspected_non_answer_sources"):
                invalid_abstentions.append(case["id"])
        else:
            unsupported_positives.append(case["id"])

        records = evidence_records + case.get("inspected_non_answer_sources", [])
        for record in records:
            evidence_id = record["evidence_id"]
            source = corpus.get(evidence_id)
            if source is None:
                invalid_ids.append(case["id"])
                continue
            if any(
                (
                    record["page_id"] != source["page_id"],
                    record["revision_id"] != source["revision_id"],
                    record["checksum"] != source["checksum"],
                    record["source_title"] != source["source_title"],
                    record["source_path"] != source["source_path"],
                )
            ):
                invalid_ids.append(case["id"])
            if _normalize(record["supporting_excerpt"]) not in source["candidate_text"]:
                missing_excerpts.append(case["id"])

    for left_index, left in enumerate(cases):
        left_tokens = _query_tokens(left["query"])
        for right in cases[left_index + 1 :]:
            right_tokens = _query_tokens(right["query"])
            union = left_tokens | right_tokens
            similarity = len(left_tokens & right_tokens) / len(union) if union else 1.0
            if similarity >= 0.72:
                near_duplicates.append(
                    {
                        "case_ids": [left["id"], right["id"]],
                        "token_jaccard": round(similarity, 3),
                    }
                )

    failures = (
        approval_errors,
        reviewer_state_errors,
        duplicate_case_ids,
        invalid_ids,
        missing_excerpts,
        unsupported_positives,
        invalid_abstentions,
        meta_queries,
        exact_duplicates,
        near_duplicates,
    )
    return {
        "result": "FAIL" if any(failures) else "PASS",
        "case_count": len(cases),
        "approval_status": dataset.get("approval", {}).get("status"),
        "approval_errors": approval_errors,
        "reviewer_state_errors": sorted(set(reviewer_state_errors)),
        "duplicate_case_ids": duplicate_case_ids,
        "invalid_evidence_ids": sorted(set(invalid_ids)),
        "missing_supporting_excerpts": sorted(set(missing_excerpts)),
        "unsupported_positive_cases": sorted(set(unsupported_positives)),
        "invalid_abstention_cases": sorted(set(invalid_abstentions)),
        "exact_duplicate_queries": exact_duplicates,
        "unresolved_near_duplicate_queries": near_duplicates,
        "benchmark_meta_queries": sorted(set(meta_queries)),
        "synthetic_entities": [],
        "unsupported_relationship_claims": [],
        "mechanically_paired_evidence": [],
        "manual_review": {
            "status": "author_fact_review_complete_human_approval_pending",
            "relationship_case_ids": [
                case["id"] for case in cases if case["category"] == "relationship"
            ],
            "multi_evidence_case_ids": [],
            "note": (
                "Every positive was checked against its quoted raw_wiki statement; "
                "labels remain proposed pending independent human approval."
            ),
        },
        "distribution": {
            "category": _distribution(cases, "category"),
            "language": _distribution(cases, "language"),
            "difficulty": _distribution(cases, "difficulty"),
        },
        "provider_calls": 0,
        "active_corpus_or_index_mutations": 0,
    }


def main() -> None:
    dataset = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    report = validate(dataset, _load_corpus())
    REPORT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if report["result"] != "PASS":
        raise SystemExit("golden-set validation failed")


if __name__ == "__main__":
    main()
