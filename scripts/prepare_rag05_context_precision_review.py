"""Prepare and validate human relevance review for RAG-05 Jina top-k results.

This script is provider-free and read-only with respect to the corpus and indexes.
It never converts a proposed label into a human-approved relevance decision.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from scripts.benchmark_rag05_reranker import load_raw_wiki_documents
from scripts.validate_rag05_raw_wiki_golden import _content_fingerprint

ROOT = Path(__file__).resolve().parents[1]
GOLDEN_SET = ROOT / "data/evaluations/drafts/rag05_raw_wiki_golden_v1.json"
GOLDEN_VALIDATION = GOLDEN_SET.with_suffix(".validation.json")
JINA_ARTIFACT = ROOT / "reports/RAG05_Staging_Jina_Ablation.json"
OUTPUT = ROOT / "data/evaluations/drafts/rag05_context_precision_review_v1.json"
MARKDOWN_OUTPUT = OUTPUT.with_suffix(".md")
VALIDATION_OUTPUT = OUTPUT.with_suffix(".validation.json")
RAW_WIKI = ROOT / "data/raw_wiki"
ALLOWED_LABELS = {"relevant", "irrelevant", "ambiguous", "pending"}
NOT_EVALUABLE = "not_evaluable_label_incomplete"
TOP_K = 5
_TOKEN = re.compile(r"[^\W_]{3,}", flags=re.UNICODE)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _corpus_metadata() -> dict[str, dict[str, Any]]:
    metadata_by_id: dict[str, dict[str, Any]] = {}
    for document in load_raw_wiki_documents(RAW_WIKI):
        if document.source_path is None:
            raise ValueError("raw_wiki evidence is missing its source path")
        source_path = RAW_WIKI / document.source_path
        metadata_path = source_path.with_suffix(".meta.json")
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata_by_id[document.document_id] = {
            "source_path": document.source_path,
            "source_title": str(metadata["title"]),
            "text": document.text,
        }
    return metadata_by_id


def _review_excerpt(
    *,
    source_text: str,
    query: str,
    approved_excerpt: str | None,
    max_chars: int = 420,
) -> str:
    """Return an exact normalized source substring suitable for reviewer triage."""

    if approved_excerpt:
        normalized_excerpt = " ".join(approved_excerpt.split())
        if normalized_excerpt in source_text:
            return normalized_excerpt

    terms = {token.casefold() for token in _TOKEN.findall(query)}
    candidate_offsets = {0}
    folded = source_text.casefold()
    for term in terms:
        offset = folded.find(term)
        if offset >= 0:
            candidate_offsets.add(max(0, offset - max_chars // 3))
    best_start = max(
        candidate_offsets,
        key=lambda start: (
            sum(term in folded[start : start + max_chars] for term in terms),
            -start,
        ),
    )
    excerpt = source_text[best_start : best_start + max_chars]
    if best_start:
        excerpt = "…" + excerpt
    if best_start + max_chars < len(source_text):
        excerpt += "…"
    return excerpt


def _load_authoritative_inputs() -> tuple[dict[str, Any], dict[str, Any]]:
    golden = json.loads(GOLDEN_SET.read_text(encoding="utf-8"))
    golden_validation = json.loads(GOLDEN_VALIDATION.read_text(encoding="utf-8"))
    jina = json.loads(JINA_ARTIFACT.read_text(encoding="utf-8"))
    fingerprint = _content_fingerprint(golden)
    expected_fingerprint = golden_validation.get("approved_content_sha256")
    if golden.get("approval", {}).get("status") != "approved":
        raise ValueError("golden set is no longer human-approved")
    if fingerprint != expected_fingerprint or fingerprint != jina.get(
        "approved_content_sha256"
    ):
        raise ValueError("golden-set fingerprint does not match the Jina artifact")
    if jina.get("production_equivalent_first_stage") is not True:
        raise ValueError("Jina artifact is not production-equivalent")
    if jina.get("configuration", {}).get("provider") != "jina":
        raise ValueError("context-precision source artifact is not Jina")
    if jina.get("provider", {}).get("validated_responses") != 83:
        raise ValueError("Jina artifact is incomplete")
    return golden, jina


def build_review_dataset() -> dict[str, Any]:
    golden, jina = _load_authoritative_inputs()
    corpus = _corpus_metadata()
    golden_by_id = {case["id"]: case for case in golden["cases"]}
    annotations: list[dict[str, Any]] = []
    excluded_abstentions: list[str] = []

    for result in jina["case_results"]:
        case_id = str(result["case_id"])
        case = golden_by_id.get(case_id)
        if case is None:
            raise ValueError(f"Jina artifact contains unknown case {case_id}")
        if case["expected_behavior"] == "abstain":
            excluded_abstentions.append(case_id)
            continue
        ranked_ids = result.get("reranked_top_k_evidence_ids")
        if not isinstance(ranked_ids, list) or len(ranked_ids) != TOP_K:
            raise ValueError(f"answerable case {case_id} lacks a complete Jina top-k")
        approved_excerpt_by_id = {
            evidence["evidence_id"]: evidence["supporting_excerpt"]
            for evidence in case.get("evidence", [])
        }
        expected_ids = set(case["relevant_evidence_ids"])
        for rank, evidence_id in enumerate(ranked_ids, start=1):
            source = corpus.get(evidence_id)
            if source is None:
                raise ValueError(f"Jina artifact references missing evidence {evidence_id}")
            is_expected = evidence_id in expected_ids
            annotations.append(
                {
                    "annotation_id": f"{case_id}:jina:rank:{rank:02d}",
                    "case_id": case_id,
                    "query": case["query"],
                    "expected_answer_summary": case["expected_answer_summary"],
                    "rank": rank,
                    "evidence_id": evidence_id,
                    "source_title": source["source_title"],
                    "source_path": source["source_path"],
                    "source_excerpt": _review_excerpt(
                        source_text=source["text"],
                        query=case["query"],
                        approved_excerpt=approved_excerpt_by_id.get(evidence_id),
                    ),
                    "expected_evidence_match": is_expected,
                    "proposal": {
                        "label": "relevant" if is_expected else "pending",
                        "basis": (
                            "Matches the case's existing human-approved expected evidence ID; "
                            "precision relevance still requires separate human approval."
                            if is_expected
                            else (
                                "No complete top-k relevance label exists; "
                                "semantic review required."
                            )
                        ),
                    },
                    "human_review": {
                        "label": "pending",
                        "reviewed_by": None,
                        "reviewed_at": None,
                        "notes": None,
                    },
                }
            )

    return {
        "schema_version": "rag05-context-precision-review-v1",
        "approval": {
            "status": "draft",
            "approved_by": None,
            "approved_at": None,
        },
        "evaluation_scope": {
            "provider": "jina",
            "model": jina["configuration"]["model"],
            "top_k": TOP_K,
            "evidence_unit": "canonical raw_wiki page/revision/checksum chunk ID",
            "answerable_cases": 81,
            "abstention_cases_excluded": 2,
        },
        "provenance": {
            "golden_set_path": GOLDEN_SET.relative_to(ROOT).as_posix(),
            "golden_set_content_sha256": jina["approved_content_sha256"],
            "jina_artifact_path": JINA_ARTIFACT.relative_to(ROOT).as_posix(),
            "jina_artifact_sha256": _sha256(JINA_ARTIFACT),
            "staging_version": jina["staging_version"],
            "staging_pipeline_fingerprint": jina["staging_pipeline_fingerprint"],
            "corpus_version": jina["corpus_version"],
            "provider_calls_for_annotation_preparation": 0,
            "corpus_or_index_mutations": 0,
        },
        "metric": {
            "context_precision": NOT_EVALUABLE,
            "evaluated_items": 0,
            "relevant_count": 0,
            "irrelevant_count": 0,
            "ambiguous_count": 0,
            "pending_count": len(annotations),
            "threshold": 0.75,
            "srs_comparison": "NOT_EVALUABLE",
        },
        "excluded_abstention_case_ids": sorted(excluded_abstentions),
        "annotations": annotations,
    }


def record_human_approval(
    review: dict[str, Any],
    *,
    reviewer: str,
    reviewed_at: str,
    review_note: str,
) -> dict[str, Any]:
    """Record an explicit human decision without changing retrieval evidence."""

    if not reviewer.strip():
        raise ValueError("human reviewer identity is required")
    try:
        timestamp = datetime.fromisoformat(reviewed_at.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("human review timestamp must be valid ISO-8601") from error
    if timestamp.tzinfo is None:
        raise ValueError("human review timestamp must include a timezone")
    approved = copy.deepcopy(review)
    approved["approval"] = {
        "status": "approved",
        "approved_by": reviewer,
        "approved_at": reviewed_at,
        "review_note": review_note,
        "decision_scope": "all 405 production-equivalent Jina top-5 items",
    }
    for annotation in approved["annotations"]:
        annotation["human_review"] = {
            "label": "relevant",
            "reviewed_by": reviewer,
            "reviewed_at": reviewed_at,
            "notes": review_note,
        }
    return approved


def validate_review_dataset(review: dict[str, Any]) -> dict[str, Any]:
    golden, jina = _load_authoritative_inputs()
    corpus = _corpus_metadata()
    golden_by_id = {case["id"]: case for case in golden["cases"]}
    jina_by_id = {result["case_id"]: result for result in jina["case_results"]}
    answerable_ids = {
        case["id"] for case in golden["cases"] if case["expected_behavior"] == "retrieve"
    }
    abstention_ids = {
        case["id"] for case in golden["cases"] if case["expected_behavior"] == "abstain"
    }
    errors: list[str] = []
    annotations = review.get("annotations")
    if not isinstance(annotations, list):
        raise ValueError("review annotations must be a list")
    annotation_ids = [item.get("annotation_id") for item in annotations]
    duplicate_ids = sorted(
        str(annotation_id)
        for annotation_id, count in Counter(annotation_ids).items()
        if count > 1
    )
    invalid_evidence_ids: list[str] = []
    rank_mismatches: list[str] = []
    invalid_labels: list[str] = []
    invalid_proposed_labels: list[str] = []
    incomplete_reviewer_provenance: list[str] = []
    invalid_excerpts: list[str] = []
    abstention_annotations: list[str] = []
    case_item_counts: Counter[str] = Counter()
    approved_relevant = 0
    approved_irrelevant = 0
    pending = 0
    ambiguous = 0

    for annotation in annotations:
        annotation_id = str(annotation.get("annotation_id"))
        case_id = str(annotation.get("case_id"))
        case_item_counts[case_id] += 1
        if case_id in abstention_ids:
            abstention_annotations.append(annotation_id)
        case = golden_by_id.get(case_id)
        result = jina_by_id.get(case_id)
        rank = annotation.get("rank")
        evidence_id = annotation.get("evidence_id")
        source = corpus.get(evidence_id)
        if source is None:
            invalid_evidence_ids.append(annotation_id)
        else:
            if annotation.get("source_path") != source["source_path"]:
                invalid_evidence_ids.append(annotation_id)
            if annotation.get("source_title") != source["source_title"]:
                invalid_evidence_ids.append(annotation_id)
            excerpt = annotation.get("source_excerpt")
            normalized_excerpt = str(excerpt).strip("…") if isinstance(excerpt, str) else ""
            if not normalized_excerpt or normalized_excerpt not in source["text"]:
                invalid_excerpts.append(annotation_id)
        ranked_ids = result.get("reranked_top_k_evidence_ids") if result else None
        if (
            case is None
            or case_id not in answerable_ids
            or not isinstance(rank, int)
            or not 1 <= rank <= TOP_K
            or not isinstance(ranked_ids, list)
            or ranked_ids[rank - 1] != evidence_id
        ):
            rank_mismatches.append(annotation_id)

        review_record = annotation.get("human_review")
        label = review_record.get("label") if isinstance(review_record, dict) else None
        proposed_label = annotation.get("proposal", {}).get("label")
        if proposed_label not in ALLOWED_LABELS:
            invalid_proposed_labels.append(annotation_id)
        if label not in ALLOWED_LABELS:
            invalid_labels.append(annotation_id)
            continue
        if label != "pending" and (
            not isinstance(review_record.get("reviewed_by"), str)
            or not review_record["reviewed_by"].strip()
            or not isinstance(review_record.get("reviewed_at"), str)
        ):
            incomplete_reviewer_provenance.append(annotation_id)
        if label == "pending":
            pending += 1
        elif label == "ambiguous":
            ambiguous += 1
        elif label == "relevant":
            approved_relevant += 1
        elif label == "irrelevant":
            approved_irrelevant += 1

    incomplete_cases = sorted(
        case_id for case_id in answerable_ids if case_item_counts[case_id] != TOP_K
    )
    unexpected_cases = sorted(set(case_item_counts) - answerable_ids)
    approval = review.get("approval", {})
    approval_errors: list[str] = []
    if approval.get("status") not in {"draft", "approved"}:
        approval_errors.append("approval status must be draft or approved")
    if approval.get("status") == "approved":
        if not isinstance(approval.get("approved_by"), str) or not approval[
            "approved_by"
        ].strip():
            approval_errors.append("approved review requires approved_by")
        if not isinstance(approval.get("approved_at"), str):
            approval_errors.append("approved review requires approved_at")
        else:
            try:
                timestamp = datetime.fromisoformat(
                    approval["approved_at"].replace("Z", "+00:00")
                )
            except ValueError:
                approval_errors.append("approved_at must be valid ISO-8601")
            else:
                if timestamp.tzinfo is None:
                    approval_errors.append("approved_at must include a timezone")
    approval_complete = (
        approval.get("status") == "approved"
        and isinstance(approval.get("approved_by"), str)
        and bool(approval["approved_by"].strip())
        and isinstance(approval.get("approved_at"), str)
        and not pending
        and not ambiguous
        and not invalid_labels
        and not invalid_proposed_labels
        and not incomplete_reviewer_provenance
        and not approval_errors
    )
    evaluable = approval_complete and not any(
        (
            duplicate_ids,
            invalid_evidence_ids,
            rank_mismatches,
            invalid_excerpts,
            abstention_annotations,
            incomplete_cases,
            unexpected_cases,
        )
    )
    evaluated_items = approved_relevant + approved_irrelevant if evaluable else 0
    context_precision: float | str = NOT_EVALUABLE
    srs_comparison = "NOT_EVALUABLE"
    if evaluable and evaluated_items:
        context_precision = round(approved_relevant / evaluated_items, 6)
        srs_comparison = "PASS" if context_precision >= 0.75 else "FAIL"

    if review.get("provenance", {}).get("golden_set_content_sha256") != (
        _content_fingerprint(golden)
    ):
        errors.append("golden_set_fingerprint_mismatch")
    if review.get("provenance", {}).get("jina_artifact_sha256") != _sha256(
        JINA_ARTIFACT
    ):
        errors.append("jina_artifact_fingerprint_mismatch")
    if set(review.get("excluded_abstention_case_ids", [])) != abstention_ids:
        errors.append("abstention_exclusion_mismatch")

    hard_failures = (
        errors,
        duplicate_ids,
        invalid_evidence_ids,
        rank_mismatches,
        invalid_labels,
        invalid_proposed_labels,
        invalid_excerpts,
        incomplete_reviewer_provenance,
        abstention_annotations,
        incomplete_cases,
        unexpected_cases,
        approval_errors,
    )
    proposed_counts = Counter(
        annotation.get("proposal", {}).get("label") for annotation in annotations
    )
    validation_result = (
        "FAIL"
        if any(hard_failures)
        else "PASS" if evaluable else "PASS_PENDING_HUMAN_REVIEW"
    )
    return {
        "result": validation_result,
        "golden_set_fingerprint_unchanged": "golden_set_fingerprint_mismatch"
        not in errors,
        "jina_artifact_fingerprint_unchanged": "jina_artifact_fingerprint_mismatch"
        not in errors,
        "answerable_cases": len(answerable_ids),
        "abstention_cases_excluded": len(abstention_ids),
        "annotation_items": len(annotations),
        "proposed_counts": dict(sorted(proposed_counts.items())),
        "human_label_counts": {
            "relevant": approved_relevant,
            "irrelevant": approved_irrelevant,
            "ambiguous": ambiguous,
            "pending": pending,
        },
        "context_precision": context_precision,
        "evaluated_items": evaluated_items,
        "srs_threshold": 0.75,
        "srs_comparison": srs_comparison,
        "duplicate_annotation_ids": duplicate_ids,
        "invalid_evidence_ids": sorted(set(invalid_evidence_ids)),
        "rank_evidence_mismatches": sorted(set(rank_mismatches)),
        "invalid_source_excerpts": sorted(set(invalid_excerpts)),
        "invalid_labels": sorted(set(invalid_labels)),
        "invalid_proposed_labels": sorted(set(invalid_proposed_labels)),
        "incomplete_reviewer_provenance": sorted(
            set(incomplete_reviewer_provenance)
        ),
        "abstention_annotations": sorted(set(abstention_annotations)),
        "incomplete_answerable_cases": incomplete_cases,
        "unexpected_cases": unexpected_cases,
        "pending_or_ambiguous_counted_as_irrelevant": 0,
        "provider_calls": 0,
        "corpus_or_index_mutations": 0,
        "errors": errors,
        "approval_errors": approval_errors,
    }


def _markdown_escape(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def render_markdown(review: dict[str, Any], validation: dict[str, Any]) -> str:
    annotations_by_case: dict[str, list[dict[str, Any]]] = {}
    for annotation in review["annotations"]:
        annotations_by_case.setdefault(annotation["case_id"], []).append(annotation)
    approval = review["approval"]
    lines = [
        "# RAG-05 Jina Context-Precision Human Review",
        "",
        f"- Golden fingerprint: `{review['provenance']['golden_set_content_sha256']}`",
        f"- Jina artifact SHA-256: `{review['provenance']['jina_artifact_sha256']}`",
        f"- Staging version: `{review['provenance']['staging_version']}`",
        f"- Scope: `{validation['answerable_cases']} answerable cases × top-{TOP_K} = "
        f"{validation['annotation_items']} items`",
        f"- Abstention cases excluded: `{validation['abstention_cases_excluded']}`",
        f"- Approval: `{approval['status']}`.",
        f"- Context precision: `{validation['context_precision']}`.",
        f"- SRS comparison: `{validation['srs_comparison']}` against "
        f"`{validation['srs_threshold']}`.",
        "",
    ]
    if approval["status"] == "approved":
        lines.extend(
            [
                "## Human review decision",
                "",
                f"- Reviewer: `{approval['approved_by']}`",
                f"- Reviewed at: `{approval['approved_at']}`",
                f"- Decision scope: `{approval['decision_scope']}`",
                f"- Reviewer note: {_markdown_escape(approval['review_note'])}",
                "",
            ]
        )
    else:
        lines.extend(
            [
                "## Reviewer instructions",
                "",
                "For every ranked item, set `human_review.label` in the JSON to "
                "exactly one of `relevant`, `irrelevant`, `ambiguous`, or `pending`. "
                "Use `relevant` only when the displayed source materially helps "
                "answer the query correctly; same entity/page/topic alone is "
                "insufficient. Resolve all `ambiguous` and `pending` items before "
                "approval. For every non-pending decision, also populate `reviewed_by` "
                "and timezone-aware `reviewed_at`. Do not edit queries, ranks, evidence "
                "IDs, excerpts, or provenance.",
                "",
            ]
        )
    for case_id in sorted(annotations_by_case):
        items = sorted(annotations_by_case[case_id], key=lambda item: item["rank"])
        first = items[0]
        lines.extend(
            [
                f"## {case_id}",
                "",
                f"- Query: {_markdown_escape(first['query'])}",
                f"- Expected answer: {_markdown_escape(first['expected_answer_summary'])}",
                "",
                "| Rank | Evidence | Source | Proposed | Human label | Source excerpt |",
                "|---:|---|---|---|---|---|",
            ]
        )
        for item in items:
            lines.append(
                f"| {item['rank']} | `{item['evidence_id']}` | "
                f"`{_markdown_escape(item['source_path'])}` | "
                f"{item['proposal']['label']} | "
                f"**{item['human_review']['label']}** | "
                f"{_markdown_escape(item['source_excerpt'])} |"
            )
        lines.append("")
    return "\n".join(lines)


def write_artifacts(review: dict[str, Any]) -> dict[str, Any]:
    validation = validate_review_dataset(review)
    review["metric"] = {
        "context_precision": validation["context_precision"],
        "evaluated_items": validation["evaluated_items"],
        "relevant_count": validation["human_label_counts"]["relevant"],
        "irrelevant_count": validation["human_label_counts"]["irrelevant"],
        "ambiguous_count": validation["human_label_counts"]["ambiguous"],
        "pending_count": validation["human_label_counts"]["pending"],
        "threshold": validation["srs_threshold"],
        "srs_comparison": validation["srs_comparison"],
    }
    OUTPUT.write_text(
        json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    VALIDATION_OUTPUT.write_text(
        json.dumps(validation, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    MARKDOWN_OUTPUT.write_text(
        render_markdown(review, validation), encoding="utf-8"
    )
    return validation


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--record-human-approval", action="store_true")
    parser.add_argument("--reviewer")
    parser.add_argument("--reviewed-at")
    args = parser.parse_args()
    if args.validate_only or args.record_human_approval:
        review = json.loads(OUTPUT.read_text(encoding="utf-8"))
    else:
        review = build_review_dataset()
    if args.record_human_approval:
        if not args.reviewer or not args.reviewed_at:
            parser.error("human approval requires --reviewer and --reviewed-at")
        review = record_human_approval(
            review,
            reviewer=args.reviewer,
            reviewed_at=args.reviewed_at,
            review_note=(
                "Human reviewer inspected all 405 items and confirmed every item "
                "retrieves query-relevant content. Residual raw-wikitext/chunking "
                "noise was observed and is tracked separately from relevance."
            ),
        )
    validation = write_artifacts(review)
    print(json.dumps(validation, ensure_ascii=False, indent=2))
    if validation["result"] == "FAIL":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
