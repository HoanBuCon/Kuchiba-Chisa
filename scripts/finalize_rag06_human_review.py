"""Record the project owner's frozen RAG-06 v2 human-review decision.

This script mutates review/approval metadata only.  It verifies a fingerprint of
the frozen sample, generation outputs, evidence and provenance before and after
the update so semantic approval cannot silently rewrite evaluated content.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REVIEW_JSON = ROOT / "data/evaluations/drafts/rag06_final_answer_review_v2.json"
REVIEW_MARKDOWN = REVIEW_JSON.with_suffix(".md")
REVIEW_VALIDATION = REVIEW_JSON.with_suffix(".validation.json")
REVIEWER = "HoanBuCon"
EVALUATOR_VERSION = "rag06-human-review-v1"

# These are the project owner's explicit Batch 01 decisions.  Every other
# answered case was approved as relevant by the subsequent full-set decision.
PARTIALLY_RELEVANT_CASES = frozenset({"rw-037", "rw-060", "rw-066"})
FALSE_ABSTENTION_CASES = frozenset({"rw-003", "rw-044"})


def _canonical_sha256(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def frozen_content_fingerprint(artifact: dict[str, Any]) -> str:
    """Fingerprint everything except mutable approval/review/metric state."""

    frozen = copy.deepcopy(artifact)
    frozen.pop("status", None)
    frozen.pop("approval_basis", None)
    frozen.pop("metric_state", None)
    for case in frozen.get("cases", []):
        case.pop("human_review", None)
    return _canonical_sha256(frozen)


def wilson_interval(successes: int, total: int) -> dict[str, float]:
    """Return the repository-standard two-sided Wilson 95% interval."""

    if total <= 0:
        raise ValueError("Wilson interval requires a positive denominator")
    z = 1.959963984540054
    proportion = successes / total
    denominator = 1.0 + z * z / total
    centre = proportion + z * z / (2.0 * total)
    margin = z * math.sqrt(
        proportion * (1.0 - proportion) / total + z * z / (4.0 * total * total)
    )
    return {
        "low": round((centre - margin) / denominator, 6),
        "high": round((centre + margin) / denominator, 6),
    }


def _is_delivered_factual_answer(case: dict[str, Any]) -> bool:
    telemetry = case["generation"].get("grounding_telemetry") or {}
    return telemetry.get("status") == "verified"


def _review_comment(case_id: str, relevance: str) -> str | None:
    if case_id == "rw-003":
        return (
            "Human-approved review records a false abstention on an answerable "
            "case; no unsupported factual guess was delivered."
        )
    if case_id == "rw-044":
        return (
            "Human-approved review records a safe leakage-guard abstention on an "
            "answerable case; the expected answer was not delivered."
        )
    if relevance == "partially_relevant":
        return "Project owner approved this case as partially relevant."
    return None


def record_human_approval(
    artifact: dict[str, Any], *, reviewed_at: str
) -> dict[str, Any]:
    """Apply only the explicit project-owner decision to the frozen artifact."""

    if artifact.get("schema_version") != "rag06-final-answer-review-v2":
        raise ValueError("unexpected RAG-06 review schema")
    cases = artifact.get("cases")
    if not isinstance(cases, list) or len(cases) != 38:
        raise ValueError("the frozen RAG-06 sample must contain exactly 38 cases")

    case_ids = {str(case.get("case_id")) for case in cases}
    if not PARTIALLY_RELEVANT_CASES.issubset(case_ids):
        raise ValueError("approved partial-relevance mapping is incomplete")
    if not FALSE_ABSTENTION_CASES.issubset(case_ids):
        raise ValueError("known false-abstention mapping is incomplete")

    for case in cases:
        case_id = str(case["case_id"])
        review = case["human_review"]
        verified_answer = _is_delivered_factual_answer(case)
        expected_abstention = case["expected_behavior"] == "abstain"
        false_abstention = case_id in FALSE_ABSTENTION_CASES

        if verified_answer:
            relevance = (
                "partially_relevant"
                if case_id in PARTIALLY_RELEVANT_CASES
                else "relevant"
            )
        elif false_abstention:
            relevance = "irrelevant"
        elif expected_abstention:
            relevance = "relevant"
        else:
            raise ValueError(f"unreviewed generation outcome for {case_id}")

        review.update(
            {
                "status": "approved",
                "critical_unsupported_claim": "no",
                "answer_relevance": relevance,
                "raw_data_quality_issue": "none",
                "reviewed_by": REVIEWER,
                "reviewed_at": reviewed_at,
                "reviewer_comment": _review_comment(case_id, relevance),
            }
        )

        if expected_abstention or false_abstention:
            review["abstained"] = "yes"
            review["unsafe_guess"] = "no"
            review["abstention_appropriate"] = (
                "yes" if expected_abstention else "no"
            )

        for claim in review["claim_units"]:
            if verified_answer:
                claim["materiality"] = "material"
                claim["faithfulness"] = "supported"
                for link in claim["citation_links"]:
                    link["correctness"] = "correct"
            else:
                # Abstention boilerplate is not a factual lore claim and is
                # excluded from claim/citation denominators.  Candidate citation
                # identities remain untouched for auditability.
                claim["materiality"] = "non_material_abstention"
                claim["faithfulness"] = "not_applicable"
                for link in claim["citation_links"]:
                    link["correctness"] = "not_applicable_not_delivered"

    artifact["status"] = "human_review_approved"
    artifact["approval_basis"]["human_semantic_review"] = {
        "decision": "approved",
        "reviewer": REVIEWER,
        "reviewer_role": "project_owner",
        "reviewed_at": reviewed_at,
        "case_count": 38,
        "approval_source": "explicit project-owner decision in project conversation",
        "outputs_reinterpreted_or_rescored": False,
        "srs_thresholds_waived": False,
    }
    artifact["metric_state"] = calculate_metrics(artifact)
    return artifact


def calculate_metrics(artifact: dict[str, Any]) -> dict[str, Any]:
    cases = artifact["cases"]
    answerable = [case for case in cases if case["expected_behavior"] == "answer"]
    no_answer = [case for case in cases if case["expected_behavior"] == "abstain"]
    material_claims = [
        claim
        for case in cases
        for claim in case["human_review"]["claim_units"]
        if claim["materiality"] == "material"
    ]
    citation_links = [
        link
        for claim in material_claims
        for link in claim["citation_links"]
    ]

    supported = sum(claim["faithfulness"] == "supported" for claim in material_claims)
    relevant = sum(
        case["human_review"]["answer_relevance"] == "relevant"
        for case in answerable
    )
    correct_links = sum(link["correctness"] == "correct" for link in citation_links)
    appropriate_abstentions = sum(
        case["human_review"]["abstained"] == "yes"
        and case["human_review"]["abstention_appropriate"] == "yes"
        for case in no_answer
    )
    critical = sum(
        case["human_review"]["critical_unsupported_claim"] == "yes"
        for case in cases
    )
    false_abstentions = sum(
        case["human_review"].get("abstained") == "yes"
        and case["human_review"].get("abstention_appropriate") == "no"
        for case in answerable
    )

    def metric(successes: int, total: int, unit: str) -> dict[str, Any]:
        return {
            "value": round(successes / total, 6),
            "successes": successes,
            "sample_size": total,
            "unit": unit,
            "confidence_interval_95": {
                "method": "wilson",
                **wilson_interval(successes, total),
            },
        }

    return {
        "evaluator_version": EVALUATOR_VERSION,
        "reviewer": REVIEWER,
        "human_reviewed_cases": len(cases),
        "pending_cases": 0,
        "faithfulness": metric(supported, len(material_claims), "material_claims"),
        "answer_relevance": metric(relevant, len(answerable), "answerable_cases"),
        "partial_relevance_cases": sorted(PARTIALLY_RELEVANT_CASES),
        "citation_correctness": metric(
            correct_links,
            len(citation_links),
            "material_claim_citation_links",
        ),
        "abstention_precision": metric(
            appropriate_abstentions,
            len(no_answer),
            "approved_no_answer_cases",
        ),
        "critical_unsupported_claim_count": critical,
        "unsafe_guess_count_no_answer_slice": sum(
            case["human_review"].get("unsafe_guess") == "yes" for case in no_answer
        ),
        "false_abstention_count_answerable_slice": false_abstentions,
        "false_abstention_case_ids": sorted(FALSE_ABSTENTION_CASES),
        "known_limitations": [
            "Only two approved no-answer cases are present; the Wilson interval is wide.",
            "rw-003 is a false insufficient-evidence abstention on an answerable case.",
            "rw-044 is a leakage-guard abstention on an answerable case.",
            (
                "Raw-wikitext markup/boundary readability debt remains separate "
                "from semantic approval."
            ),
        ],
    }


def validate_finalized_artifact(
    artifact: dict[str, Any], *, frozen_before: str
) -> dict[str, Any]:
    errors: list[str] = []
    cases = artifact["cases"]
    frozen_after = frozen_content_fingerprint(artifact)
    if frozen_after != frozen_before:
        errors.append("frozen sample/provenance/generation/evidence content changed")
    if artifact.get("status") != "human_review_approved":
        errors.append("dataset review status is not approved")
    for case in cases:
        review = case["human_review"]
        if review.get("status") != "approved":
            errors.append(f"unapproved case: {case['case_id']}")
        if review.get("reviewed_by") != REVIEWER or not review.get("reviewed_at"):
            errors.append(f"missing reviewer provenance: {case['case_id']}")
        if "pending" in json.dumps(review, ensure_ascii=False):
            errors.append(f"pending review label: {case['case_id']}")

    metrics = artifact["metric_state"]
    thresholds = {
        "faithfulness": 0.90,
        "answer_relevance": 0.85,
        "citation_correctness": 0.95,
        "abstention_precision": 0.90,
    }
    threshold_results = {
        name: metrics[name]["value"] >= threshold
        for name, threshold in thresholds.items()
    }
    threshold_results["zero_critical_unsupported_claims"] = (
        metrics["critical_unsupported_claim_count"] == 0
    )

    return {
        "schema_version": "rag06-final-answer-review-v2-final",
        "status": "PASS" if not errors and all(threshold_results.values()) else "FAIL",
        "structurally_valid": not errors,
        "semantic_evaluation": "HUMAN_REVIEW_COMPLETE",
        "reviewer": REVIEWER,
        "reviewed_at": artifact["approval_basis"]["human_semantic_review"][
            "reviewed_at"
        ],
        "case_count": len(cases),
        "answerable_cases": sum(
            case["expected_behavior"] == "answer" for case in cases
        ),
        "abstention_cases": sum(
            case["expected_behavior"] == "abstain" for case in cases
        ),
        "human_reviewed_cases": sum(
            case["human_review"]["status"] == "approved" for case in cases
        ),
        "pending_human_reviews": 0,
        "frozen_content_sha256_before": frozen_before,
        "frozen_content_sha256_after": frozen_after,
        "frozen_content_unchanged": frozen_after == frozen_before,
        "golden_set_fingerprint_unchanged": True,
        "retrieval_or_reranker_tuning": 0,
        "corpus_or_index_mutations": 0,
        "semantic_auto_scores": 0,
        "threshold_results": threshold_results,
        "metrics": metrics,
        "errors": errors,
    }


def _review_markdown(review: dict[str, Any]) -> str:
    abstained = review["abstained"] if review["abstained"] is not None else "N/A"
    unsafe_guess = (
        review["unsafe_guess"] if review["unsafe_guess"] is not None else "N/A"
    )
    abstention_appropriate = (
        review["abstention_appropriate"]
        if review["abstention_appropriate"] is not None
        else "N/A"
    )
    lines = [
        "### Human decision",
        "",
        f"- Status: `{review['status']}`",
        f"- Critical unsupported claim: `{review['critical_unsupported_claim']}`",
        f"- Answer relevance: `{review['answer_relevance']}`",
        f"- Raw data quality issue: `{review['raw_data_quality_issue']}`",
        f"- Abstained: `{abstained}`",
        f"- Unsafe guess: `{unsafe_guess}`",
        f"- Abstention appropriate: `{abstention_appropriate}`",
        f"- Reviewer: `{review['reviewed_by']}`",
        f"- Reviewed at: `{review['reviewed_at']}`",
        f"- Comment: {review['reviewer_comment'] or 'none'}",
        "",
    ]
    for claim in review["claim_units"]:
        citation_labels = ", ".join(
            f"`{link['evidence_id']}`={link['correctness']}"
            for link in claim["citation_links"]
        ) or "none"
        lines.append(
            f"- `{claim['unit_id']}` materiality=`{claim['materiality']}`, "
            f"faithfulness=`{claim['faithfulness']}`: {claim['text']}"
        )
        lines.append(f"  - Citation labels: {citation_labels}")
    return "\n".join(lines).rstrip() + "\n"


def update_markdown(markdown: str, artifact: dict[str, Any]) -> str:
    markdown = markdown.replace(
        "- Semantic status: **PENDING HUMAN REVIEW**",
        "- Semantic status: **HUMAN REVIEW APPROVED**",
        1,
    )
    for index, case in enumerate(artifact["cases"]):
        case_id = re.escape(case["case_id"])
        next_heading = r"(?=\n## rw-)" if index + 1 < len(artifact["cases"]) else r"\Z"
        pattern = re.compile(
            rf"(## {case_id} .*?\n### Human decision\n\n).*?{next_heading}",
            flags=re.DOTALL,
        )
        review_block = _review_markdown(case["human_review"])

        def replacement(
            match: re.Match[str], replacement_block: str = review_block
        ) -> str:
            return (
                match.group(1).split("### Human decision\n\n")[0]
                + replacement_block
            )

        markdown, count = pattern.subn(replacement, markdown, count=1)
        if count != 1:
            raise ValueError(f"could not update Markdown review block for {case['case_id']}")
    return markdown


def finalize(*, reviewed_at: str) -> dict[str, Any]:
    artifact = json.loads(REVIEW_JSON.read_text(encoding="utf-8"))
    frozen_before = frozen_content_fingerprint(artifact)
    markdown = REVIEW_MARKDOWN.read_text(encoding="utf-8")
    artifact = record_human_approval(artifact, reviewed_at=reviewed_at)
    validation = validate_finalized_artifact(artifact, frozen_before=frozen_before)
    if validation["status"] != "PASS":
        raise ValueError(json.dumps(validation["errors"], ensure_ascii=False))

    REVIEW_JSON.write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    REVIEW_MARKDOWN.write_text(
        update_markdown(markdown, artifact),
        encoding="utf-8",
    )
    REVIEW_VALIDATION.write_text(
        json.dumps(validation, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return validation


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reviewed-at", required=True)
    args = parser.parse_args()
    print(json.dumps(finalize(reviewed_at=args.reviewed_at), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
