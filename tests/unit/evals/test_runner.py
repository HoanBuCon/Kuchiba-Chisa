"""Runner scores, skips and reports cases without a real model (STD-TEST-003)."""

import json

import httpx
import pytest

from evals.dataset import GoldenCase, GoldenSet
from evals.report import render_markdown, write_report
from evals.runner import manual_review_sample, run_golden_set
from evals.scoring import Status
from evals.targets import (
    HttpChatTarget,
    Observation,
    TargetError,
    UnsupportedCaseError,
    pages_from_evidence_ids,
)


def _golden(cases: list[dict[str, object]]) -> GoldenSet:
    return GoldenSet.model_validate(
        {
            "dataset_version": "test.1",
            "source_snapshot": "snapshot",
            "approval": {"status": "draft"},
            "abstain_markers": ["không biết"],
            "cases": cases,
        }
    )


LORE = {
    "id": "lore-001",
    "category": "lore_single_hop",
    "language": "vi",
    "turns": [{"message": "Chisa thuộc hệ gì?"}],
    "expected_facts": [["havoc"]],
    "relevant_pages": [{"title": "Chisa", "pageid": 31283}],
    "verified": True,
}
ABSTAIN = {
    "id": "oos-001",
    "category": "out_of_scope",
    "language": "vi",
    "expected_behavior": "abstain",
    "turns": [{"message": "Nhóm máu của Chisa?"}],
}
MEMORY = {
    "id": "memory-001",
    "category": "memory",
    "language": "vi",
    "turns": [{"session": 1, "message": "a"}, {"session": 2, "message": "b"}],
    "expected_facts": [["b"]],
}


class ScriptedTarget:
    name = "scripted"

    def __init__(self, answers: dict[str, Observation | Exception]) -> None:
        self._answers = answers

    async def answer(self, case: GoldenCase) -> Observation:
        outcome = self._answers[case.id]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


@pytest.mark.asyncio
async def test_run_scores_answers_abstentions_and_skips() -> None:
    golden = _golden([LORE, ABSTAIN, MEMORY])
    target = ScriptedTarget(
        {
            "lore-001": Observation("Chisa thuộc hệ Havoc, Senpai.", evidence_pages=(1, 31283)),
            "oos-001": Observation("Em không biết điều đó, Senpai."),
            "memory-001": UnsupportedCaseError("multi-session"),
        }
    )
    report = await run_golden_set(target, golden, golden.cases)

    results = {result.case_id: result for result in report.cases}
    assert results["lore-001"].correct and results["lore-001"].hit_at_5
    assert results["lore-001"].reciprocal_rank == 0.5
    assert results["oos-001"].correct and results["oos-001"].abstained
    assert results["memory-001"].status is Status.SKIPPED
    assert report.overall.n_scored == 2 and report.overall.accuracy == 1.0
    assert report.overall.abstain_precision == 1.0
    assert report.unverified_cases == ["memory-001", "oos-001"]


@pytest.mark.asyncio
async def test_hallucinated_answer_to_unanswerable_question_is_wrong() -> None:
    golden = _golden([ABSTAIN])
    target = ScriptedTarget({"oos-001": Observation("Nhóm máu của Chisa là AB.")})
    report = await run_golden_set(target, golden, golden.cases)
    assert not report.cases[0].correct
    assert report.overall.abstain_precision is None


@pytest.mark.asyncio
async def test_target_errors_are_recorded_not_raised() -> None:
    golden = _golden([LORE])
    report = await run_golden_set(
        ScriptedTarget({"lore-001": TargetError("boom")}), golden, golden.cases
    )
    assert report.cases[0].status is Status.ERROR
    assert report.overall.n_error == 1 and report.overall.accuracy is None


def test_manual_review_sample_is_stable_and_sized() -> None:
    ids = [f"lore-{n:03d}" for n in range(1, 21)]
    assert manual_review_sample(ids) == manual_review_sample(list(reversed(ids)))
    assert len(manual_review_sample(ids)) == 4
    assert manual_review_sample([]) == []


def test_pages_from_evidence_ids_keeps_rank_order_without_duplicates() -> None:
    ids = [
        "raw_wiki:37370:1:00000000000000aa:chunk:002",
        "memory:abc",
        "raw_wiki:31283:9:00000000000000bb:chunk:000",
        "raw_wiki:37370:1:00000000000000aa:chunk:005",
    ]
    assert pages_from_evidence_ids(ids) == (37370, 31283)


@pytest.mark.asyncio
async def test_http_target_uses_a_fresh_anonymous_session_per_case() -> None:
    tokens = iter(["token-1", "token-2"])
    seen_auth: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/auth/anonymous-session":
            return httpx.Response(200, json={"access_token": next(tokens)})
        seen_auth.append(request.headers["Authorization"])
        citations = ["raw_wiki:31283:1:00000000000000aa:chunk:000"]
        return httpx.Response(200, json={"response": "Havoc, Senpai.", "citations": citations})

    case = GoldenCase.model_validate(LORE)
    async with httpx.AsyncClient(
        base_url="http://chisa", transport=httpx.MockTransport(handler)
    ) as client:
        target = HttpChatTarget(client)
        first = await target.answer(case)
        await target.answer(case)
        with pytest.raises(UnsupportedCaseError):
            await target.answer(GoldenCase.model_validate(MEMORY))

    assert first.evidence_pages == (31283,)
    assert seen_auth == ["Bearer token-1", "Bearer token-2"]


@pytest.mark.asyncio
async def test_http_target_wraps_transport_failures() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    async with httpx.AsyncClient(
        base_url="http://chisa", transport=httpx.MockTransport(handler)
    ) as client:
        with pytest.raises(TargetError, match="anonymous-session"):
            await HttpChatTarget(client).answer(GoldenCase.model_validate(LORE))


@pytest.mark.asyncio
async def test_report_files_are_written(tmp_path) -> None:
    golden = _golden([LORE])
    target = ScriptedTarget({"lore-001": Observation("Havoc")})
    report = await run_golden_set(target, golden, golden.cases)

    json_path, markdown_path = write_report(report, tmp_path, "run")

    assert (
        json.loads(json_path.read_text(encoding="utf-8"))["evaluator_version"]
        == report.evaluator_version
    )
    assert "| **overall** | 1/1 |" in render_markdown(report)
    assert markdown_path.exists()
