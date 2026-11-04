"""The grounding judge: which answers it sees and how verdicts become QUAL-001/002 numbers."""

import json

from app.domain.interfaces.llm_provider import LLMPurpose
from evals.dataset import Category, GoldenCase, Language, Turn
from evals.judge import (
    MAX_QUOTE_CHARS,
    Statement,
    Verdict,
    is_uncited_answer,
    judge_prompt,
    judgeable,
    parse_verdict,
    summarize,
)
from evals.scoring import score_case
from evals.targets import Observation

CITATION = {"evidence_id": "wiki:1:a", "quote": "Chisa studies at Startorch Academy."}


def _case(**changes) -> dict:
    base = {
        "case_id": "lore-1",
        "status": "scored",
        "abstained": False,
        "answer": "Chisa học ở Startorch.",
        "citations": [CITATION],
    }
    return {**base, **changes}


def _statement(text="s", supported=True, serious=False) -> dict:
    return {"text": text, "supported": supported, "serious": serious}


def test_only_answers_with_citations_are_judged() -> None:
    assert judgeable(_case())
    assert not judgeable(_case(abstained=True))
    assert not judgeable(_case(status="skipped"))
    assert not judgeable(_case(citations=[]))


def test_answers_without_citations_are_counted_apart() -> None:
    assert is_uncited_answer(_case(citations=[]))
    assert not is_uncited_answer(_case())
    assert not is_uncited_answer(_case(citations=[], abstained=True))


def test_prompt_carries_answer_and_bounded_sources_as_data() -> None:
    long_quote = {"evidence_id": "wiki:1:a", "quote": "x" * (MAX_QUOTE_CHARS + 50)}

    prompt = judge_prompt("Chisa học ở đâu?", _case(citations=[long_quote]))

    audit = json.loads(prompt.user_message)
    assert audit["answer"] == "Chisa học ở Startorch."
    assert len(audit["sources"][0]["text"]) == MAX_QUOTE_CHARS
    assert prompt.purpose is LLMPurpose.CONTEXT_ASSESSMENT
    assert prompt.temperature == 0.0


def test_citation_the_judge_skipped_or_invented_does_not_count() -> None:
    second = {"evidence_id": "wiki:2:b", "quote": "Other."}
    parsed = {
        "statements": [_statement()],
        "citations": [
            {"evidence_id": "wiki:1:a", "supports": True},
            {"evidence_id": "wiki:9:z", "supports": True},
        ],
    }

    verdict = parse_verdict(_case(citations=[CITATION, second]), parsed)

    assert (verdict.supporting_citations, verdict.total_citations) == (1, 2)


def test_supported_statement_is_never_serious() -> None:
    parsed = {"statements": [_statement(supported=True, serious=True)], "citations": []}

    assert parse_verdict(_case(), parsed).statements[0].serious is False


def test_summary_counts_statements_citations_and_failures() -> None:
    verdicts = [
        Verdict("a", (Statement("x", True, False), Statement("y", False, True)), 1, 1),
        Verdict("b", (Statement("z", True, False),), 0, 1),
    ]

    summary = summarize(verdicts, uncited_answers=3, failed_cases=["c"])

    assert summary.groundedness == 2 / 3
    assert summary.citation_precision == 1 / 2
    assert summary.serious_statements == 1
    assert (summary.judged_cases, summary.uncited_answers) == (2, 3)
    assert summary.failed_cases == ("c",)


def test_empty_summary_has_no_score_instead_of_a_perfect_one() -> None:
    summary = summarize([], uncited_answers=0, failed_cases=[])

    assert summary.groundedness is None
    assert summary.citation_precision is None


def test_scored_case_keeps_the_citations_for_the_judge() -> None:
    case = GoldenCase(
        id="lore-001",
        category=Category.LORE_SINGLE_HOP,
        language=Language.VI,
        turns=(Turn(message="Chisa học ở đâu?"),),
        expected_facts=(("startorch",),),
        verified=True,
    )
    observation = Observation(
        answer="Senpai, Chisa học ở Startorch.", raw={"citations": [CITATION]}
    )

    assert score_case(case, observation, ()).citations == (CITATION,)
