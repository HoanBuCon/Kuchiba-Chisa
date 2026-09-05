"""Focused correctness tests for the label-independent RAG-05 formal harness."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from app.infrastructure.vector.qdrant.sparse_encoder import SparseTextEncoder
from scripts.benchmark_rag05_reranker import (
    GoldenCase,
    GoldenExpectedBehavior,
    _answerable_ranking_slice,
    _first_relevant_rank,
    _first_stage_retrieval_misses,
    _hybrid_rrf_order,
    _metric_summary,
    load_golden_dataset,
    load_raw_wiki_documents,
    validate_relevant_evidence_ids,
)

APPROVED_GOLDEN_SET = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "evaluations"
    / "drafts"
    / "rag05_raw_wiki_golden_v1.json"
)


def _write_revision(root: Path, *, page_id: int, revision_id: int, text: str) -> str:
    directory = root / "Characters" / str(page_id)
    directory.mkdir(parents=True)
    revision_path = directory / f"{page_id}_main.wikitext"
    revision_path.write_text(text, encoding="utf-8")
    revision_path.with_suffix(".meta.json").write_text(
        json.dumps({"page_id": page_id, "revision_id": revision_id}),
        encoding="utf-8",
    )
    checksum = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    return f"raw_wiki:{page_id}:{revision_id}:{checksum}:chunk:000"


def _snapshot(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _write_golden_dataset(path: Path, cases: list[dict[str, object]]) -> None:
    path.write_text(
        json.dumps(
            {
                "dataset_version": "test-v1",
                "evidence_scope": "public",
                "approval": {
                    "status": "approved",
                    "approved_by": "reviewer",
                    "approved_at": "2026-09-05T16:18:36Z",
                },
                "cases": cases,
            }
        ),
        encoding="utf-8",
    )


def _case(
    *, expected_behavior: str, relevant_evidence_ids: list[str]
) -> dict[str, object]:
    return {
        "id": "case-1",
        "query": "What is the supported fact?",
        "expected_behavior": expected_behavior,
        "relevant_evidence_ids": relevant_evidence_ids,
    }


def test_loader_accepts_answerable_case_with_positive_evidence(tmp_path: Path) -> None:
    dataset_path = tmp_path / "golden.json"
    evidence_id = "raw_wiki:10:101:0123456789abcdef:chunk:000"
    _write_golden_dataset(
        dataset_path,
        [_case(expected_behavior="retrieve", relevant_evidence_ids=[evidence_id])],
    )

    _, cases = load_golden_dataset(dataset_path)

    assert cases == [
        GoldenCase(
            "case-1",
            "What is the supported fact?",
            (evidence_id,),
            GoldenExpectedBehavior.RETRIEVE,
        )
    ]


def test_loader_accepts_abstention_case_without_positive_evidence(tmp_path: Path) -> None:
    dataset_path = tmp_path / "golden.json"
    _write_golden_dataset(
        dataset_path,
        [_case(expected_behavior="abstain", relevant_evidence_ids=[])],
    )

    _, cases = load_golden_dataset(dataset_path)

    assert cases[0].expected_behavior is GoldenExpectedBehavior.ABSTAIN
    assert cases[0].relevant_evidence_ids == ()


def test_loader_rejects_answerable_case_without_evidence(tmp_path: Path) -> None:
    dataset_path = tmp_path / "golden.json"
    _write_golden_dataset(
        dataset_path,
        [_case(expected_behavior="retrieve", relevant_evidence_ids=[])],
    )

    with pytest.raises(ValueError, match="answerable golden case needs relevant evidence"):
        load_golden_dataset(dataset_path)


def test_loader_rejects_abstention_case_with_positive_evidence(tmp_path: Path) -> None:
    dataset_path = tmp_path / "golden.json"
    _write_golden_dataset(
        dataset_path,
        [
            _case(
                expected_behavior="abstain",
                relevant_evidence_ids=[
                    "raw_wiki:10:101:0123456789abcdef:chunk:000"
                ],
            )
        ],
    )

    with pytest.raises(ValueError, match="abstention golden case cannot declare"):
        load_golden_dataset(dataset_path)


def test_approved_golden_set_loads_with_both_evaluation_slices() -> None:
    version, cases = load_golden_dataset(APPROVED_GOLDEN_SET)

    assert version == "rag05-raw-wiki-golden-v1-draft"
    assert len(cases) == 83
    assert sum(case.is_answerable for case in cases) == 81
    assert sum(not case.is_answerable for case in cases) == 2


def test_abstentions_do_not_enter_ranking_denominator_or_miss_list() -> None:
    cases = [
        GoldenCase(
            "answer-hit",
            "answerable",
            ("evidence-1",),
            GoldenExpectedBehavior.RETRIEVE,
        ),
        GoldenCase(
            "abstain",
            "no answer",
            (),
            GoldenExpectedBehavior.ABSTAIN,
        ),
        GoldenCase(
            "answer-miss",
            "answerable miss",
            ("evidence-2",),
            GoldenExpectedBehavior.RETRIEVE,
        ),
    ]
    per_case_ranks = [1, None, None]

    ranking_ranks = _answerable_ranking_slice(cases, per_case_ranks)

    assert ranking_ranks == [1, None]
    assert _metric_summary(ranking_ranks)["hit_at_1"] == 0.5
    assert _first_stage_retrieval_misses(cases, per_case_ranks) == ["answer-miss"]


def test_raw_wiki_resolution_is_deterministic_auditable_and_read_only(tmp_path: Path) -> None:
    second_id = _write_revision(
        tmp_path,
        page_id=20,
        revision_id=202,
        text="Second approved public lore revision.",
    )
    first_id = _write_revision(
        tmp_path,
        page_id=10,
        revision_id=101,
        text="First approved public lore revision.",
    )
    before = _snapshot(tmp_path)

    first_load = load_raw_wiki_documents(tmp_path)
    second_load = load_raw_wiki_documents(tmp_path)

    assert first_load == second_load
    assert [document.document_id for document in first_load] == [first_id, second_id]
    assert [document.source_path for document in first_load] == [
        "Characters/10/10_main.wikitext",
        "Characters/20/20_main.wikitext",
    ]
    assert _snapshot(tmp_path) == before


@pytest.mark.parametrize(
    "evidence_id",
    [
        "world_lore/aalto.md",
        "raw_wiki:10:101:not-a-checksum:chunk:000",
        "raw_wiki:10:101:0123456789abcdef:chunk:001",
    ],
)
def test_relevance_validation_rejects_invalid_evidence_ids(evidence_id: str) -> None:
    case = GoldenCase("case-1", "Who is Aalto?", (evidence_id,))

    with pytest.raises(ValueError, match="invalid raw_wiki evidence ID"):
        validate_relevant_evidence_ids([case], [])


def test_relevance_validation_rejects_missing_raw_wiki_revision(tmp_path: Path) -> None:
    available_id = _write_revision(
        tmp_path,
        page_id=10,
        revision_id=101,
        text="A real revision.",
    )
    missing_id = available_id.replace(":101:", ":102:")

    with pytest.raises(ValueError, match="missing raw_wiki revision"):
        validate_relevant_evidence_ids(
            [GoldenCase("case-1", "Who is Aalto?", (missing_id,))],
            load_raw_wiki_documents(tmp_path),
        )


def test_candidate_pool_and_ranking_are_independent_of_relevance_labels(
    tmp_path: Path,
) -> None:
    first_id = _write_revision(
        tmp_path,
        page_id=10,
        revision_id=101,
        text="Aalto belongs to the Black Shores.",
    )
    second_id = _write_revision(
        tmp_path,
        page_id=20,
        revision_id=202,
        text="Black Shores studies the Lament.",
    )
    documents = load_raw_wiki_documents(tmp_path)
    document_vectors = [[1.0, 0.0], [0.0, 1.0]]
    query_vector = [1.0, 0.0]
    query = "Which group does Aalto belong to?"

    original_labels = [GoldenCase("case-1", query, (first_id,))]
    changed_labels = [GoldenCase("case-1", query, (second_id,))]
    removed_labels = [GoldenCase("case-1", query, ())]
    validate_relevant_evidence_ids(original_labels, documents)
    validate_relevant_evidence_ids(changed_labels, documents)
    validate_relevant_evidence_ids(removed_labels, documents)

    rankings = [
        _hybrid_rrf_order(
            documents,
            query_vector,
            document_vectors,
            query,
            SparseTextEncoder(),
        )
        for _ in (original_labels, changed_labels, removed_labels)
    ]

    assert rankings[0] == rankings[1] == rankings[2]
    assert set(rankings[0]) == {first_id, second_id}


def test_metric_summary_preserves_ranking_metrics_without_fake_precision() -> None:
    metrics = _metric_summary([1, 2, None, 10])

    assert metrics == {
        "hit_at_1": 0.25,
        "hit_at_3": 0.5,
        "hit_at_5": 0.5,
        "mrr_at_10": 0.4,
        "context_precision": "not_evaluable_label_incomplete",
    }
    assert _first_relevant_rank(["missing"], ["first", "second"]) is None
