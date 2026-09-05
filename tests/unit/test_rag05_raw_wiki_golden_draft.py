from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DATASET_PATH = ROOT / "data" / "evaluations" / "drafts" / "rag05_raw_wiki_golden_v1.json"
CORPUS_ROOT = ROOT / "data" / "raw_wiki"
EVIDENCE_ID = re.compile(
    r"^raw_wiki:(?P<page_id>[1-9][0-9]*):(?P<revision_id>[1-9][0-9]*):"
    r"(?P<checksum>[0-9a-f]{16}):chunk:000$"
)
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


def _load_dataset() -> dict[str, Any]:
    value = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _load_corpus() -> dict[str, tuple[dict[str, Any], str, str]]:
    corpus: dict[str, tuple[dict[str, Any], str, str]] = {}
    for path in sorted(CORPUS_ROOT.rglob("*_main.wikitext")):
        metadata = json.loads(path.with_suffix(".meta.json").read_text(encoding="utf-8"))
        raw_text = path.read_text(encoding="utf-8")
        checksum = hashlib.sha256(raw_text.encode()).hexdigest()[:16]
        evidence_id = (
            f"raw_wiki:{metadata['page_id']}:{metadata['revision_id']}:" f"{checksum}:chunk:000"
        )
        corpus[evidence_id] = (
            metadata,
            _normalize(raw_text)[:1200],
            path.relative_to(CORPUS_ROOT).as_posix(),
        )
    return corpus


def test_golden_draft_stays_unapproved_and_within_target_size() -> None:
    dataset = _load_dataset()

    assert dataset["approval"] == {
        "status": "draft",
        "approved_by": None,
        "approved_at": None,
    }
    assert dataset["label_status"] == "proposed"
    assert dataset["evidence_scope"] == "public"
    assert 80 <= len(dataset["cases"]) <= 100
    assert dataset["case_count"] == len(dataset["cases"])
    assert all(case["reviewer_status"] == "pending" for case in dataset["cases"])
    assert all(case["reviewer_notes"] is None for case in dataset["cases"])


def test_positive_evidence_identity_and_excerpt_resolve_to_candidate_text() -> None:
    corpus = _load_corpus()
    dataset = _load_dataset()

    for case in dataset["cases"]:
        if case["expected_behavior"] == "abstain":
            assert case["relevant_evidence_ids"] == []
            assert case["evidence"] == []
            continue

        assert case["expected_behavior"] == "retrieve"
        assert len(case["relevant_evidence_ids"]) == len(case["evidence"]) == 1
        evidence = case["evidence"][0]
        evidence_id = evidence["evidence_id"]
        assert EVIDENCE_ID.fullmatch(evidence_id)
        assert case["relevant_evidence_ids"] == [evidence_id]
        metadata, candidate_text, source_path = corpus[evidence_id]
        assert evidence["page_id"] == metadata["page_id"]
        assert evidence["revision_id"] == metadata["revision_id"]
        assert evidence["source_title"] == metadata["title"]
        assert evidence["source_path"] == source_path
        assert _normalize(evidence["supporting_excerpt"]) in candidate_text
        assert case["expected_answer_summary"].strip()
        assert case["rationale"].strip()


def test_abstention_inspection_sources_are_real_non_answer_documents() -> None:
    corpus = _load_corpus()
    abstentions = [
        case for case in _load_dataset()["cases"] if case["expected_behavior"] == "abstain"
    ]

    assert len(abstentions) == 2
    for case in abstentions:
        assert case["relevant_evidence_ids"] == []
        assert case["evidence"] == []
        assert case["inspected_non_answer_sources"]
        for inspected in case["inspected_non_answer_sources"]:
            _, candidate_text, _ = corpus[inspected["evidence_id"]]
            assert _normalize(inspected["supporting_excerpt"]) in candidate_text


def test_queries_are_unique_natural_and_non_meta() -> None:
    queries = [case["query"] for case in _load_dataset()["cases"]]
    normalized = [_normalize(query).casefold() for query in queries]

    assert len(normalized) == len(set(normalized))
    assert not [
        query
        for query in normalized
        if any(forbidden in query for forbidden in FORBIDDEN_QUERY_TEXT)
    ]


def test_relationship_cases_have_direct_source_excerpts() -> None:
    relationship_cases = [
        case for case in _load_dataset()["cases"] if case["category"] == "relationship"
    ]

    assert relationship_cases
    assert all(case["expected_behavior"] == "retrieve" for case in relationship_cases)
    assert all(case["evidence"][0]["supporting_excerpt"] for case in relationship_cases)
    assert all(case["rationale"].strip() for case in relationship_cases)
