"""Generate a human-review packet for RAG-06 without semantic auto-scoring.

The runner reuses the approved RAG-05 golden set, frozen production-equivalent
staging candidates, the current context builder, PII boundary and generation
output guards. It never mutates the corpus/index or protected prompt content.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
import time
import uuid
from collections import Counter, defaultdict, deque
from collections.abc import AsyncIterator, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from app.config.settings import settings
from app.domain.entities.emotion import EmotionState
from app.domain.interfaces.llm_provider import BaseLLMAdapter, LLMResponse, StructuredPrompt
from app.domain.models.evidence import (
    Evidence,
    EvidenceAccess,
    EvidenceProvenance,
    EvidenceScore,
)
from app.domain.models.intent_result import ChatIntent, IntentResult
from app.domain.services.budget_mode import BudgetMode
from app.domain.services.chat_pipeline.context import ChatContext
from app.domain.services.chat_pipeline.stages.llm_generation_stage import LLMGenerationStage
from app.domain.services.chat_pipeline.stages.provider_pii_redaction_stage import (
    ProviderPiiRedactionStage,
)
from app.domain.services.context_builder import ContextBuilder
from app.domain.services.guardrails import PromptLeakageGuard
from app.domain.services.rag import RAGContext
from app.infrastructure.llm.adapters.deepseek import DeepSeekAdapter
from app.shared.utils.json_parser import robust_parse_json
from scripts.benchmark_rag05_reranker import load_raw_wiki_documents
from scripts.evaluate_rag05_staging_voyage_ablation import _load_frozen_inputs
from scripts.prepare_rag05_context_precision_review import _review_excerpt
from scripts.validate_rag05_raw_wiki_golden import _content_fingerprint

ROOT = Path(__file__).resolve().parents[1]
GOLDEN_SET = ROOT / "data/evaluations/drafts/rag05_raw_wiki_golden_v1.json"
GOLDEN_VALIDATION = GOLDEN_SET.with_suffix(".validation.json")
JINA_ARTIFACT = ROOT / "reports/RAG05_Staging_Jina_Ablation.json"
CONTEXT_REVIEW = ROOT / "data/evaluations/drafts/rag05_context_precision_review_v1.json"
OUTPUT_JSON = ROOT / "data/evaluations/drafts/rag06_final_answer_review_v2.json"
OUTPUT_MARKDOWN = OUTPUT_JSON.with_suffix(".md")
OUTPUT_VALIDATION = OUTPUT_JSON.with_suffix(".validation.json")
ANSWERABLE_SAMPLE_SIZE = 36
SCHEMA_VERSION = "rag06-final-answer-review-v2"
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?。！？])\s+|\n+")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _distribution(cases: Sequence[dict[str, Any]], field: str) -> dict[str, int]:
    return dict(sorted(Counter(str(case[field]) for case in cases).items()))


def select_review_cases(
    cases: Sequence[dict[str, Any]],
    *,
    dataset_fingerprint: str,
    answerable_sample_size: int = ANSWERABLE_SAMPLE_SIZE,
) -> list[dict[str, Any]]:
    """Select deterministic round-robin strata plus every abstention case."""

    answerable = [case for case in cases if case["expected_behavior"] == "retrieve"]
    abstentions = [case for case in cases if case["expected_behavior"] == "abstain"]
    if answerable_sample_size < 1 or answerable_sample_size > len(answerable):
        raise ValueError("answerable sample size is outside the approved dataset")

    strata: dict[tuple[str, str, str], deque[dict[str, Any]]] = {}
    grouped: defaultdict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for case in answerable:
        key = (str(case["language"]), str(case["category"]), str(case["difficulty"]))
        grouped[key].append(case)
    for key, values in grouped.items():
        values.sort(
            key=lambda case: hashlib.sha256(
                f"{dataset_fingerprint}:{case['id']}".encode()
            ).hexdigest()
        )
        strata[key] = deque(values)

    selected: list[dict[str, Any]] = []
    ordered_strata = sorted(strata)
    while len(selected) < answerable_sample_size:
        progressed = False
        for key in ordered_strata:
            if strata[key] and len(selected) < answerable_sample_size:
                selected.append(strata[key].popleft())
                progressed = True
        if not progressed:
            raise ValueError("stratified selection exhausted before reaching the target")

    return selected + sorted(abstentions, key=lambda case: str(case["id"]))


class RecordingLLMAdapter(BaseLLMAdapter):
    """Delegate to the real provider while retaining only validated response fields."""

    def __init__(self, delegate: BaseLLMAdapter) -> None:
        self._delegate = delegate
        self.last_response: LLMResponse | None = None

    async def generate(self, prompt: StructuredPrompt) -> LLMResponse:
        response = await self._delegate.generate(prompt)
        self.last_response = response
        return response

    async def stream(self, prompt: StructuredPrompt) -> AsyncIterator[str]:
        async for chunk in self._delegate.stream(prompt):
            yield chunk

    async def validate_response(
        self, raw: str, schema: dict[str, Any]
    ) -> dict[str, Any]:
        return await self._delegate.validate_response(raw, schema)

    async def estimate_tokens(self, text: str) -> int:
        return await self._delegate.estimate_tokens(text)


class _ReviewSession:
    """No-op session port; the review generation stages perform no persistence."""

    async def commit(self) -> None:
        return None


class _DeepSeekResponseCapture:
    """Capture validated envelope fields without retaining raw output or reasoning."""

    def __init__(self) -> None:
        self.last_response: LLMResponse | None = None

    def reset(self) -> None:
        self.last_response = None

    async def capture(self, response: httpx.Response) -> None:
        if response.status_code != 200:
            return
        try:
            await response.aread()
            payload = response.json()
            choice = payload["choices"][0]
            content = choice["message"].get("content", "") or ""
            parsed = robust_parse_json(content)
            if not isinstance(parsed, dict):
                parsed = {}
            usage = payload.get("usage", {})
            self.last_response = LLMResponse(
                raw_content="",
                parsed=parsed,
                input_tokens=int(usage.get("prompt_tokens", 0)),
                output_tokens=int(usage.get("completion_tokens", 0)),
                reasoning_tokens=int(
                    usage.get("completion_tokens_details", {}).get(
                        "reasoning_tokens", 0
                    )
                ),
                model=str(payload.get("model") or settings.DEEPSEEK_MODEL),
                finish_reason=str(choice.get("finish_reason") or ""),
                reasoning_content=None,
            )
        except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError):
            self.last_response = None


class _SingleAttemptDeepSeekAdapter(DeepSeekAdapter):
    """Benchmark-only fail-fast policy; production adapter defaults stay intact."""

    _MAX_RETRIES = 1


def _evidence_from_frozen_excerpt(
    *,
    evidence_id: str,
    text: str,
    source_path: str,
    rank: int,
    corpus_version: str,
) -> Evidence:
    parts = evidence_id.split(":")
    if len(parts) != 6 or parts[0] != "raw_wiki" or parts[4] != "chunk":
        raise ValueError(f"invalid frozen raw_wiki evidence ID {evidence_id}")
    return Evidence(
        evidence_id=evidence_id,
        kind="lore",
        text=text,
        provenance=EvidenceProvenance(
            source_id=evidence_id,
            source_type="raw_wiki",
            collection="lore",
            source_version=corpus_version,
            parent_id=source_path,
            page_id=int(parts[1]),
            chunk_index=int(parts[5]),
        ),
        access=EvidenceAccess(scope="public"),
        score=EvidenceScore(
            final=1.0 / rank,
            components={"frozen_jina_rank": float(rank)},
        ),
    )


def _frozen_evidence_by_case(
    *,
    dataset: dict[str, Any],
    jina: dict[str, Any],
) -> dict[str, list[Evidence]]:
    """Replay accepted ranking IDs with exact reviewer-audited source excerpts."""

    context_review = json.loads(CONTEXT_REVIEW.read_text(encoding="utf-8"))
    if context_review.get("approval", {}).get("status") != "approved":
        raise ValueError("context-precision evidence is not human-approved")
    if context_review.get("provenance", {}).get("golden_set_content_sha256") != jina.get(
        "approved_content_sha256"
    ):
        raise ValueError("context-precision evidence uses another golden set")

    annotations: defaultdict[str, dict[int, dict[str, Any]]] = defaultdict(dict)
    for annotation in context_review["annotations"]:
        if annotation.get("human_review", {}).get("label") != "relevant":
            raise ValueError("frozen context contains a non-approved relevance label")
        annotations[str(annotation["case_id"])][int(annotation["rank"])] = annotation

    corpus = {document.document_id: document for document in load_raw_wiki_documents()}
    case_by_id = {case["id"]: case for case in dataset["cases"]}
    frozen: dict[str, list[Evidence]] = {}
    for result in jina["case_results"]:
        case_id = str(result["case_id"])
        case = case_by_id[case_id]
        ranked_ids = result.get("reranked_top_k_evidence_ids")
        if not isinstance(ranked_ids, list) or len(ranked_ids) < 5:
            raise ValueError(f"frozen Jina top-k is incomplete for {case_id}")
        items: list[Evidence] = []
        for rank, evidence_id in enumerate(ranked_ids[:5], start=1):
            annotation = annotations.get(case_id, {}).get(rank)
            if annotation is not None:
                if annotation["evidence_id"] != evidence_id:
                    raise ValueError(f"review rank drift for {case_id}:{rank}")
                text = str(annotation["source_excerpt"])
                source_path = str(annotation["source_path"])
            else:
                # The context-precision review intentionally excluded abstention
                # cases. Resolve those frozen ranking IDs from the same immutable
                # raw_wiki snapshot without inventing relevance labels.
                document = corpus.get(evidence_id)
                if document is None or document.source_path is None:
                    raise ValueError(f"missing abstention evidence {evidence_id}")
                text = _review_excerpt(
                    source_text=document.text,
                    query=str(case["query"]),
                    approved_excerpt=None,
                )
                source_path = document.source_path
            items.append(
                _evidence_from_frozen_excerpt(
                    evidence_id=str(evidence_id),
                    text=text,
                    source_path=source_path,
                    rank=rank,
                    corpus_version=str(jina["corpus_version"]),
                )
            )
        frozen[case_id] = items
    return frozen


def _claim_units(answer: str, citation_ids: Sequence[str]) -> list[dict[str, Any]]:
    units = [part.strip() for part in _SENTENCE_BOUNDARY.split(answer) if part.strip()]
    return [
        {
            "unit_id": f"claim-{index:02d}",
            "text": unit,
            "materiality": "pending",
            "faithfulness": "pending",
            "citation_links": [
                {"evidence_id": evidence_id, "correctness": "pending"}
                for evidence_id in citation_ids
            ],
            "reviewer_notes": None,
        }
        for index, unit in enumerate(units, start=1)
    ]


def _build_context(case: dict[str, Any], evidence: list[Evidence]) -> ChatContext:
    reviewer_user = uuid.uuid5(uuid.NAMESPACE_URL, f"rag06-review:{case['id']}")
    emotion = EmotionState(user_id=reviewer_user)
    context_builder = ContextBuilder()
    build = context_builder.build(
        emotion=emotion,
        attachment_bonus=0.0,
        memories=[],
        lore=[item.text for item in evidence],
        history=[],
        user_message=str(case["query"]),
        intent_name=ChatIntent.LORE.value,
        budget_mode=BudgetMode.RAG,
        is_small_talk=False,
        evidence=evidence,
    )
    build.prompt.temperature = 0.5
    return ChatContext(
        session=_ReviewSession(),
        user_id=f"rag06-review-{case['id']}",
        user_message=str(case["query"]),
        emotion=emotion,
        intent_result=IntentResult(
            intents=[ChatIntent.LORE],
            confidence=1.0,
            routing_method="approved_rag06_review",
        ),
        rag_context=RAGContext(
            lore_chunks=[item.text for item in evidence],
            evidence=evidence,
        ),
        prompt=build.prompt,
        budget_audit=build.audit,
    )


def _safe_candidate_response(
    response: LLMResponse | None, prompt: StructuredPrompt
) -> tuple[str | None, bool]:
    if response is None:
        return None, False
    candidate = response.parsed.get("response")
    if not isinstance(candidate, str):
        claims = response.parsed.get("claims")
        if isinstance(claims, list):
            candidate = " ".join(
                str(claim.get("text", "")).strip()
                for claim in claims
                if isinstance(claim, dict) and str(claim.get("text", "")).strip()
            )
    if not isinstance(candidate, str) or not candidate.strip():
        return None, False
    leakage = PromptLeakageGuard().inspect(
        prompt.system,
        candidate,
        allowed_source_texts=[item.text for item in prompt.retrieved_evidence],
    )
    if leakage.leaked:
        return None, True
    return candidate, False


async def _generate_case(
    *,
    case: dict[str, Any],
    evidence: list[Evidence],
    recorder: RecordingLLMAdapter,
    response_capture: _DeepSeekResponseCapture,
) -> dict[str, Any]:
    context = _build_context(case, evidence)
    context = await ProviderPiiRedactionStage().process(context)
    if context.prompt is None:
        raise RuntimeError("provider PII boundary removed the structured prompt")
    recorder.last_response = None
    response_capture.reset()
    started = time.perf_counter()
    failure_type: str | None = None
    try:
        result = await LLMGenerationStage(llm=recorder).process(context)
        delivery_status = (
            "abstained_missing_evidence"
            if result.tool_res
            and result.tool_res.get("grounding", {}).get("status")
            == "abstained_missing_evidence"
            else "delivered"
        )
        delivered_answer = result.chisa_reply
        delivered_citations = list(result.citation_ids)
        grounding = (result.tool_res or {}).get("grounding")
    except Exception as error:
        delivery_status = "rejected_or_provider_failed"
        delivered_answer = None
        delivered_citations = []
        grounding = None
        failure_type = type(error).__name__
    elapsed_ms = (time.perf_counter() - started) * 1000

    captured_response = recorder.last_response or response_capture.last_response
    candidate_answer, leakage_redacted = _safe_candidate_response(
        captured_response, context.prompt
    )
    candidate_citations: list[str] = []
    if captured_response is not None:
        raw_citations = captured_response.parsed.get("citations")
        if isinstance(raw_citations, list):
            candidate_citations = [item for item in raw_citations if isinstance(item, str)]
        elif isinstance(captured_response.parsed.get("claims"), list):
            candidate_citations = list(
                dict.fromkeys(
                    str(claim["evidence_id"])
                    for claim in captured_response.parsed["claims"]
                    if isinstance(claim, dict)
                    and isinstance(claim.get("evidence_id"), str)
                )
            )
    review_answer = delivered_answer or candidate_answer or ""
    review_citations = delivered_citations or candidate_citations
    response = captured_response
    provider_model = settings.DEEPSEEK_MODEL
    finish_reason = None
    input_tokens = 0
    output_tokens = 0
    reasoning_tokens = 0
    if response is not None:
        provider_model = response.model
        finish_reason = response.finish_reason
        input_tokens = response.input_tokens
        output_tokens = response.output_tokens
        reasoning_tokens = response.reasoning_tokens

    return {
        "case_id": case["id"],
        "query": case["query"],
        "language": case["language"],
        "category": case["category"],
        "difficulty": case["difficulty"],
        "expected_behavior": (
            "answer" if case["expected_behavior"] == "retrieve" else "abstain"
        ),
        "expected_answer_summary": case["expected_answer_summary"],
        "selected_evidence": [
            {
                "rank": rank,
                "evidence_id": item.evidence_id,
                "source_id": item.provenance.source_id,
                "parent_id": item.provenance.parent_id,
                "text": item.text,
            }
            for rank, item in enumerate(evidence, start=1)
        ],
        "generation": {
            "delivery_status": delivery_status,
            "delivered_answer": delivered_answer,
            "delivered_citations": delivered_citations,
            "candidate_answer": candidate_answer,
            "candidate_citations": candidate_citations,
            "candidate_redacted_for_prompt_leakage": leakage_redacted,
            "failure_type": failure_type,
            "grounding_telemetry": grounding,
            "provider_model": provider_model,
            "finish_reason": finish_reason,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "reasoning_tokens": reasoning_tokens,
            "elapsed_ms": round(elapsed_ms, 3),
        },
        "human_review": {
            "status": "pending",
            "critical_unsupported_claim": "pending",
            "answer_relevance": "pending",
            "raw_data_quality_issue": "pending",
            "abstained": "pending" if case["expected_behavior"] == "abstain" else None,
            "unsafe_guess": "pending" if case["expected_behavior"] == "abstain" else None,
            "abstention_appropriate": (
                "pending" if case["expected_behavior"] == "abstain" else None
            ),
            "reviewed_by": None,
            "reviewed_at": None,
            "reviewer_comment": None,
            "claim_units": _claim_units(review_answer, review_citations),
        },
    }


def validate_review_artifact(
    artifact: dict[str, Any],
    *,
    golden: dict[str, Any],
    jina: dict[str, Any],
) -> dict[str, Any]:
    errors: list[str] = []
    cases = artifact.get("cases")
    if not isinstance(cases, list):
        raise ValueError("review artifact cases must be a list")
    golden_by_id = {case["id"]: case for case in golden["cases"]}
    jina_by_id = {case["case_id"]: case for case in jina["case_results"]}
    seen: set[str] = set()
    answerable = 0
    abstentions = 0
    evidence_items = 0
    provider_responses = 0
    prompt_leakage_redactions = 0

    for item in cases:
        case_id = item.get("case_id")
        if case_id in seen:
            errors.append(f"duplicate case: {case_id}")
            continue
        seen.add(str(case_id))
        source = golden_by_id.get(case_id)
        ranking = jina_by_id.get(case_id)
        if source is None or ranking is None:
            errors.append(f"unknown case: {case_id}")
            continue
        expected = "answer" if source["expected_behavior"] == "retrieve" else "abstain"
        if item.get("query") != source["query"] or item.get("expected_behavior") != expected:
            errors.append(f"approved case content mismatch: {case_id}")
        if expected == "answer":
            answerable += 1
        else:
            abstentions += 1
        selected = item.get("selected_evidence")
        ranked_ids = ranking.get("reranked_top_k_evidence_ids")
        if not isinstance(selected, list) or not isinstance(ranked_ids, list):
            errors.append(f"missing frozen evidence: {case_id}")
        else:
            selected_ids = [entry.get("evidence_id") for entry in selected]
            if selected_ids != ranked_ids[:5]:
                errors.append(f"rank/evidence mismatch: {case_id}")
            evidence_items += len(selected)
        review = item.get("human_review", {})
        if review.get("status") != "pending" or review.get("reviewed_by") is not None:
            errors.append(f"semantic review was auto-approved: {case_id}")
        generation = item.get("generation", {})
        if generation.get("candidate_redacted_for_prompt_leakage"):
            prompt_leakage_redactions += 1
            if generation.get("candidate_answer") is not None:
                errors.append(f"leaked candidate persisted: {case_id}")
        if generation.get("input_tokens", 0) > 0:
            provider_responses += 1

    expected_abstention_ids = {
        case["id"] for case in golden["cases"] if case["expected_behavior"] == "abstain"
    }
    if answerable != ANSWERABLE_SAMPLE_SIZE:
        errors.append("answerable sample size changed")
    if abstentions != len(expected_abstention_ids) or not expected_abstention_ids.issubset(seen):
        errors.append("not all approved abstention cases are present")
    if artifact.get("provenance", {}).get("approved_content_sha256") != _content_fingerprint(
        golden
    ):
        errors.append("golden-set fingerprint mismatch")
    if artifact.get("provenance", {}).get("staging_version") != jina.get(
        "staging_version"
    ):
        errors.append("staging version mismatch")

    return {
        "schema_version": SCHEMA_VERSION,
        "status": "PASS" if not errors else "FAIL",
        "structurally_valid": not errors,
        "semantic_evaluation": "NOT_EVALUATED_PENDING_HUMAN_REVIEW",
        "case_count": len(cases),
        "answerable_cases": answerable,
        "abstention_cases": abstentions,
        "evidence_items": evidence_items,
        "provider_http_responses_captured": provider_responses,
        "prompt_leakage_candidates_redacted": prompt_leakage_redactions,
        "pending_human_reviews": sum(
            item.get("human_review", {}).get("status") == "pending" for item in cases
        ),
        "golden_set_fingerprint_unchanged": not any(
            error == "golden-set fingerprint mismatch" for error in errors
        ),
        "retrieval_or_reranker_tuning": 0,
        "corpus_or_index_mutations": 0,
        "semantic_auto_scores": 0,
        "errors": errors,
    }


def _markdown(artifact: dict[str, Any], validation: dict[str, Any]) -> str:
    lines = [
        "# RAG-06 Final-answer Human Review v2",
        "",
        f"- Generated: `{artifact['generated_at']}`",
        f"- Dataset fingerprint: `{artifact['provenance']['approved_content_sha256']}`",
        f"- Sample: {artifact['sample']['total_cases']} cases "
        f"({artifact['sample']['answerable_cases']} answerable, "
        f"{artifact['sample']['abstention_cases']} abstention)",
        f"- Provider/model: `{artifact['generation_configuration']['provider']}` / "
        f"`{artifact['generation_configuration']['model']}`",
        f"- Structural validation: **{validation['status']}**",
        "- Semantic status: **PENDING HUMAN REVIEW**",
        "",
        "Do not use external game knowledge. Judge only the query, expected behavior, "
        "displayed evidence, delivered/candidate answer and citations. An unsupported "
        "non-abstaining answer on a no-answer case is blocking.",
        "",
    ]
    for item in artifact["cases"]:
        generation = item["generation"]
        lines.extend(
            [
                f"## {item['case_id']} — {item['query']}",
                "",
                f"- Expected behavior: `{item['expected_behavior']}`",
                f"- Expected summary: {item['expected_answer_summary']}",
                f"- Delivery status: `{generation['delivery_status']}`",
                f"- Failure type: `{generation['failure_type'] or 'none'}`",
                f"- Provider/model: `{generation['provider_model']}`",
                f"- Tokens: input {generation['input_tokens']}, output "
                f"{generation['output_tokens']}, reasoning {generation['reasoning_tokens']}",
                "",
                "### Evidence",
                "",
            ]
        )
        for evidence in item["selected_evidence"]:
            text = str(evidence["text"]).replace("\n", " ")
            lines.extend(
                [
                    f"**Rank {evidence['rank']} — `{evidence['evidence_id']}`**",
                    "",
                    f"> {text}",
                    "",
                ]
            )
        answer = generation["delivered_answer"] or generation["candidate_answer"]
        if generation["candidate_redacted_for_prompt_leakage"]:
            answer = "[REDACTED: prompt-leakage guard triggered]"
        lines.extend(
            [
                "### Answer for review",
                "",
                answer or "[No validated candidate answer available]",
                "",
                "Citations: "
                + json.dumps(
                    generation["delivered_citations"]
                    or generation["candidate_citations"],
                    ensure_ascii=False,
                ),
                "",
                "### Human decision",
                "",
                "- Status: `pending`",
                "- Critical unsupported claim: `pending`",
                "- Answer relevance: `pending`",
                "- Raw data quality issue: `pending`",
                "- Unsafe guess (abstention cases): `pending`",
                "- Reviewer/comment: `pending`",
                "",
            ]
        )
        for claim in item["human_review"]["claim_units"]:
            lines.append(
                f"- `{claim['unit_id']}` materiality=`pending`, "
                f"faithfulness=`pending`: {claim['text']}"
            )
        lines.append("")
    return "\n".join(lines)


async def run(*, answerable_sample_size: int = ANSWERABLE_SAMPLE_SIZE) -> dict[str, Any]:
    if answerable_sample_size != ANSWERABLE_SAMPLE_SIZE:
        raise ValueError("RAG-06 v2 sample size is frozen at 36 answerable cases")
    if settings.LLM_PROVIDER != "deepseek" or not settings.DEEPSEEK_API_KEY:
        raise RuntimeError("current DeepSeek provider credential is unavailable")

    dataset, _, _ = _load_frozen_inputs()
    jina = json.loads(JINA_ARTIFACT.read_text(encoding="utf-8"))
    validation = json.loads(GOLDEN_VALIDATION.read_text(encoding="utf-8"))
    fingerprint = _content_fingerprint(dataset)
    if fingerprint != validation.get("approved_content_sha256"):
        raise ValueError("approved golden-set validation fingerprint changed")
    if fingerprint != jina.get("approved_content_sha256"):
        raise ValueError("Jina artifact uses another approved golden set")
    if jina.get("production_equivalent_first_stage") is not True:
        raise ValueError("Jina source artifact is not production-equivalent")

    selected_raw = select_review_cases(
        dataset["cases"],
        dataset_fingerprint=fingerprint,
        answerable_sample_size=answerable_sample_size,
    )
    jina_by_id = {case["case_id"]: case for case in jina["case_results"]}
    frozen_evidence = _frozen_evidence_by_case(dataset=dataset, jina=jina)
    response_capture = _DeepSeekResponseCapture()
    http_client = httpx.AsyncClient(
        timeout=10.0,
        follow_redirects=True,
        event_hooks={"response": [response_capture.capture]},
    )
    # Evaluation cases are independent. A single attempt preserves the first
    # provider outcome and prevents schema failures from being hidden by retries.
    # The production adapter class/default remains unchanged.
    raw_adapter = _SingleAttemptDeepSeekAdapter(http_client=http_client)
    protected_paths = [
        ROOT / "app/domain/services/context_builder.py",
        ROOT / "app/domain/services/persona_loader.py",
        ROOT / "data/lore/character_lore/chisa_personality.md",
        ROOT / "data/lore/relationship_lore/rover.md",
        ROOT / "data/lore/relationship_lore/sumika.md",
    ]
    protected_before = {
        path.relative_to(ROOT).as_posix(): _sha256(path) for path in protected_paths
    }
    try:
        recorder = RecordingLLMAdapter(raw_adapter)
        generated: list[dict[str, Any]] = []
        for case in selected_raw:
            case_id = str(case["id"])
            evidence = frozen_evidence[case_id]
            result = await _generate_case(
                case=case,
                evidence=evidence,
                recorder=recorder,
                response_capture=response_capture,
            )
            result["retrieval_latency_ms"] = jina_by_id[case_id][
                "total_retrieval_latency_ms"
            ]
            result["retrieval_context_source"] = (
                "accepted frozen production-equivalent Jina top-5 ranking with "
                "human-reviewed exact normalized raw_wiki excerpts"
            )
            generated.append(result)
    finally:
        await http_client.aclose()

    protected_after = {path.relative_to(ROOT).as_posix(): _sha256(path) for path in protected_paths}
    if protected_before != protected_after:
        raise RuntimeError("protected prompt/persona/relationship content changed")

    selected_answerable = [
        case for case in selected_raw if case["expected_behavior"] == "retrieve"
    ]
    selected_abstentions = [
        case for case in selected_raw if case["expected_behavior"] == "abstain"
    ]
    artifact = {
        "schema_version": SCHEMA_VERSION,
        "status": "pending_human_review",
        "generated_at": datetime.now(UTC).astimezone().isoformat(),
        "approval_basis": {
            "protocol": "RAG-06 Human Review Protocol v1",
            "approved_by": "user/project owner",
            "approval_scope": "generate frozen review artifact and structural validation only",
            "semantic_outputs_preapproved": False,
            "srs_thresholds_waived": False,
        },
        "provenance": {
            "golden_set_path": GOLDEN_SET.relative_to(ROOT).as_posix(),
            "approved_content_sha256": fingerprint,
            "jina_artifact_path": JINA_ARTIFACT.relative_to(ROOT).as_posix(),
            "jina_artifact_sha256": _sha256(JINA_ARTIFACT),
            "context_review_path": CONTEXT_REVIEW.relative_to(ROOT).as_posix(),
            "context_review_sha256": _sha256(CONTEXT_REVIEW),
            "staging_version": jina["staging_version"],
            "staging_pipeline_fingerprint": jina["staging_pipeline_fingerprint"],
            "corpus_version": jina["corpus_version"],
            "protected_content_sha256": protected_after,
        },
        "sample": {
            "selection_method": (
                "deterministic SHA-256 ordering within language/category/difficulty "
                "strata, round-robin across strata; all approved abstentions included"
            ),
            "selection_seed": fingerprint,
            "answerable_cases": len(selected_answerable),
            "abstention_cases": len(selected_abstentions),
            "total_cases": len(selected_raw),
            "full_set_cases": len(dataset["cases"]),
            "full_set_required_by_srs": False,
            "language_distribution": _distribution(selected_raw, "language"),
            "category_distribution": _distribution(selected_raw, "category"),
            "difficulty_distribution": _distribution(selected_raw, "difficulty"),
            "case_ids": [case["id"] for case in selected_raw],
        },
        "generation_configuration": {
            "provider": settings.LLM_PROVIDER,
            "model": settings.DEEPSEEK_MODEL,
            "deep_thinking": settings.DEEP_THINKING,
            "temperature": 0.5,
            "context_builder": "current application ContextBuilder",
            "pii_boundary": "ProviderPiiRedactionStage",
            "output_boundary": "LLMGenerationStage guards",
            "evaluation_case_isolation": True,
            "benchmark_provider_attempts_per_case": 1,
            "production_retry_defaults_changed": False,
            "retrieval_context_replay": (
                "accepted frozen production-equivalent Jina ranking; exact "
                "normalized source excerpts approved in the context review"
            ),
            "production_equivalent_first_stage": True,
            "end_to_end_production_equivalent": False,
            "retrieval_parameters_changed": False,
            "reranker_parameters_changed": False,
        },
        "metric_state": {
            "faithfulness": "NOT_EVALUATED_PENDING_HUMAN_REVIEW",
            "answer_relevance": "NOT_EVALUATED_PENDING_HUMAN_REVIEW",
            "citation_correctness": "NOT_EVALUATED_PENDING_HUMAN_REVIEW",
            "abstention_precision": "NOT_EVALUATED_PENDING_HUMAN_REVIEW",
            "unsafe_guesses": "NOT_EVALUATED_PENDING_HUMAN_REVIEW",
        },
        "cases": generated,
    }
    structural = validate_review_artifact(artifact, golden=dataset, jina=jina)
    OUTPUT_JSON.write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")
    OUTPUT_VALIDATION.write_text(
        json.dumps(structural, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    OUTPUT_MARKDOWN.write_text(_markdown(artifact, structural), encoding="utf-8")
    if structural["status"] != "PASS":
        raise RuntimeError("RAG-06 review artifact failed structural validation")
    return structural


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--answerable-sample-size", type=int, default=ANSWERABLE_SAMPLE_SIZE)
    args = parser.parse_args()
    result = asyncio.run(run(answerable_sample_size=args.answerable_sample_size))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
