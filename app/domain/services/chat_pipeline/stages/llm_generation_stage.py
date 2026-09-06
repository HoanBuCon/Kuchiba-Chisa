import asyncio
from collections.abc import Awaitable, Callable

from app.config.settings import settings
from app.domain.context import llm_call_purpose
from app.domain.interfaces.llm_provider import (
    BaseLLMAdapter,
    LLMInvalidResponseError,
    LLMResponse,
    StructuredPrompt,
)
from app.domain.interfaces.tracker import IPipelineTracker
from app.domain.models.intent_result import ChatIntent
from app.domain.services.attachment_manifest import resolve_attachment_manifests
from app.domain.services.chat_pipeline.context import ChatContext
from app.domain.services.chat_pipeline.stage import PipelineStage
from app.domain.services.guardrails import (
    CitationValidationError,
    ClaimEvidenceGuard,
    ClaimEvidenceValidationError,
    EvidenceCitationGuard,
    GroundedOutputAssembler,
    GroundedOutputValidationError,
    PromptLeakageGuard,
    build_grounded_response_schema,
)
from app.shared.utils.logger import get_logger
from app.shared.utils.token_estimator import TokenEstimator

log = get_logger(__name__)

_GROUNDED_ABSTENTION = (
    "Mình chưa có đủ bằng chứng trong nguồn hiện tại để trả lời chính xác. "
    "Bạn có thể cung cấp thêm ngữ cảnh hoặc hỏi theo cách khác không?"
)
_GROUNDED_INTENTS = {
    ChatIntent.KNOWLEDGE_OR_TASK,
    ChatIntent.LORE,
    ChatIntent.MEMORY,
}

class LLMGenerationStage(PipelineStage):
    """
    Stage 7: LLM Generation (streaming or non-streaming) and token control.
    """
    def __init__(
        self,
        llm: BaseLLMAdapter,
        llm_logger_callback: (
            Callable[[StructuredPrompt, LLMResponse], Awaitable[None]] | None
        ) = None,
        pipeline_tracker: IPipelineTracker | None = None,
        output_leakage_guard: PromptLeakageGuard | None = None,
        citation_guard: EvidenceCitationGuard | None = None,
        claim_evidence_guard: ClaimEvidenceGuard | None = None,
        grounded_output_assembler: GroundedOutputAssembler | None = None,
    ):
        self.llm = llm
        self.llm_logger_callback = llm_logger_callback
        self.pipeline_tracker = pipeline_tracker
        self.output_leakage_guard = output_leakage_guard or PromptLeakageGuard()
        self.citation_guard = citation_guard or EvidenceCitationGuard()
        self.claim_evidence_guard = claim_evidence_guard or ClaimEvidenceGuard()
        self.grounded_output_assembler = (
            grounded_output_assembler
            or GroundedOutputAssembler(self.claim_evidence_guard)
        )

    async def process(self, context: ChatContext) -> ChatContext:
        if context.is_cached_answer:
            if context.on_token and context.chisa_reply:
                for token in context.chisa_reply:
                    if asyncio.iscoroutinefunction(context.on_token):
                        await context.on_token(token)
                    else:
                        context.on_token(token)
            return context

        prompt = context.prompt
        if prompt is None:
            raise RuntimeError("LLMGenerationStage requires a prompt from ContextBuildingStage.")
        if self._requires_grounded_evidence(context) and not prompt.retrieved_evidence:
            return await self._abstain_for_missing_evidence(context)

        if self._requires_grounded_evidence(context):
            sentiment_schema = prompt.response_schema.get("properties", {}).get(
                "sentiment"
            )
            if not isinstance(sentiment_schema, dict):
                raise RuntimeError("Grounded generation requires the sentiment schema")
            prompt = prompt.model_copy(
                update={
                    "response_schema": build_grounded_response_schema(
                        evidence_ids=[
                            item.evidence_id for item in prompt.retrieved_evidence
                        ],
                        sentiment_schema=sentiment_schema,
                    ),
                    "output_contract_name": "submit_grounded_answer",
                    "temperature": 0.0,
                }
            )
            context.prompt = prompt
            
        log.info("Generating response with structured LLM")
        llm_call_purpose.set("chat_response")
        
        if context.on_token:
            raw_chunks = []
            raw_response = ""
            parsed = {}
            error_to_raise = None
            
            try:
                async for chunk in self.llm.stream(prompt):
                    raw_chunks.append(chunk)
                
                raw_response = "".join(raw_chunks)
                parsed = await self.llm.validate_response(raw_response, prompt.response_schema)
            except Exception as e:
                error_to_raise = e
            
            est_input = (
                TokenEstimator.estimate(prompt.system)
                + TokenEstimator.estimate_messages(prompt.history)
                + TokenEstimator.estimate(prompt.user_message)
            )
            est_output = TokenEstimator.estimate(raw_response)

            reasoning_content = None
            if "<think>" in raw_response and "</think>" in raw_response:
                start_idx = raw_response.find("<think>") + 7
                end_idx = raw_response.find("</think>")
                if end_idx > start_idx:
                    reasoning_content = raw_response[start_idx:end_idx].strip()

            response = LLMResponse(
                raw_content=raw_response,
                parsed=parsed,
                input_tokens=est_input,
                output_tokens=est_output,
                model=getattr(self.llm, "_model", "unknown"),
                finish_reason="stop",
                reasoning_content=reasoning_content,
            )

            try:
                if self.llm_logger_callback:
                    await self.llm_logger_callback(prompt, response)
            except Exception as log_ex:
                log.warning("Failed to log streaming transaction", error=str(log_ex))
                
            if error_to_raise:
                raise error_to_raise
        else:
            try:
                response = await self.llm.generate(prompt)
            except Exception as gen_err:
                if context.has_images:
                    log.warning(
                        "Vision LLM call encountered an issue, activating In-Character Kuudere Resilience Fallback",
                        error=str(gen_err),
                        user_id=context.user_id,
                    )
                    context.vision_failed = True
                    # Create fallback prompt: strip images and inject in-character explanation
                    fallback_prompt = prompt.model_copy(deep=True)
                    fallback_prompt.images = []
                    fallback_prompt.system += (
                        "\n\n[HỆ THỐNG THỊ GIÁC: Tạm thời không thể tải hoặc phân tích bức ảnh này do lỗi đường truyền mạng. "
                        "Hãy để Chisa ứng biến tự nhiên theo phong thái Kuudere (ví dụ: 'Mạng của Học viện Startorch đang hơi chập chờn / Mắt Forte của em bị nhiễu sóng nên em chưa nhìn rõ ảnh Senpai vừa gửi, Senpai có thể miêu tả sơ qua hoặc lát gửi lại cho em xem nha~') và trả lời câu hỏi của Senpai bình thường.]"
                    )
                    response = await self.llm.generate(fallback_prompt)
                else:
                    raise gen_err

        grounded_envelope = None
        chisa_reply: str
        if prompt.output_contract_name == "submit_grounded_answer":
            manifests = resolve_attachment_manifests(context.retrieved_images)
            try:
                grounded_envelope = self.grounded_output_assembler.assemble(
                    payload=response.parsed,
                    evidence=prompt.retrieved_evidence,
                    attachment_ids=[item.attachment_id for item in manifests],
                    abstention_answer=_GROUNDED_ABSTENTION,
                )
            except (GroundedOutputValidationError, ValueError):
                log.warning("Generated response rejected by grounded output contract")
                return await self._abstain_for_rejected_output(
                    context,
                    status="abstained_invalid_grounding",
                )
            chisa_reply = grounded_envelope.answer
        else:
            raw_reply = response.parsed.get("response")
            chisa_reply = raw_reply if isinstance(raw_reply, str) else ""
        
        # Fallback if parsing has mismatched JSON key but correct raw JSON string
        if not chisa_reply and response.parsed:
            for val in response.parsed.values():
                if isinstance(val, str) and val.strip():
                    chisa_reply = val
                    break
                    
        # Defense against raw JSON string leaking through as message text
        if chisa_reply.strip().startswith("{") and ('"response"' in chisa_reply or "'response'" in chisa_reply):
            from app.shared.utils.json_parser import robust_parse_json
            inner_parsed = robust_parse_json(chisa_reply)
            if inner_parsed and isinstance(inner_parsed, dict) and inner_parsed.get("response"):
                chisa_reply = inner_parsed["response"]
        
        # Enforce output token limit control
        estimated_tokens = TokenEstimator.estimate(chisa_reply)
        if estimated_tokens > settings.MAX_RESPONSE_TOKENS:
            log.warning(
                "Bot response exceeded maximum output token limit. Truncating.",
                user_id=context.user_id,
                estimated_tokens=estimated_tokens,
                limit=settings.MAX_RESPONSE_TOKENS
            )
            chisa_reply = TokenEstimator.trim_to_budget(
                chisa_reply,
                settings.MAX_RESPONSE_TOKENS,
                suffix="... (phản hồi bị cắt ngắn do vượt quá giới hạn độ dài)"
            )

        if not chisa_reply.strip():
            raw_preview = (response.raw_content or "")[:300]
            parsed_keys = list(response.parsed.keys()) if response.parsed else []
            log.error(
                "LLM returned empty or unparseable response in production pipeline",
                user_id=context.user_id,
                raw_preview=raw_preview,
                parsed_keys=parsed_keys,
                model=getattr(self.llm, "_model", "unknown"),
                finish_reason=response.finish_reason,
            )
            raise ValueError(
                f"Empty response from LLM (model={getattr(self.llm, '_model', 'unknown')}, "
                f"finish_reason={response.finish_reason}, parsed_keys={parsed_keys}, "
                f"raw_preview={raw_preview[:100]})"
            )

        leakage_assessment = self.output_leakage_guard.inspect(
            prompt.system,
            chisa_reply,
            allowed_source_texts=[item.text for item in prompt.retrieved_evidence],
        )
        if leakage_assessment.leaked:
            log.warning(
                "Generated response rejected by prompt leakage guard",
                response_fingerprint=leakage_assessment.fingerprint,
            )
            if grounded_envelope is not None:
                return await self._abstain_for_rejected_output(
                    context,
                    status="abstained_output_leakage",
                )
            raise LLMInvalidResponseError("Response rejected by output safety checks")

        if grounded_envelope is not None and grounded_envelope.abstained:
            citation_ids = []
        else:
            try:
                citation_input: object = response.parsed.get("citations")
                if grounded_envelope is not None:
                    citation_input = grounded_envelope.citations
                citation_ids = self.citation_guard.validate(
                    citation_input, prompt.retrieved_evidence
                )
            except CitationValidationError as error:
                log.warning("Generated response rejected by citation guard")
                raise LLMInvalidResponseError(
                    "Response rejected by grounding checks"
                ) from error

        grounding = None
        if grounded_envelope is None or not grounded_envelope.abstained:
            try:
                grounding = self._verify_grounding(
                    context=context,
                    answer=chisa_reply,
                    citation_ids=citation_ids,
                )
            except ClaimEvidenceValidationError as error:
                log.warning("Generated response rejected by claim-evidence guard")
                raise LLMInvalidResponseError(
                    "Response rejected by grounding checks"
                ) from error

        if context.on_token:
            for token in chisa_reply:
                if asyncio.iscoroutinefunction(context.on_token):
                    await context.on_token(token)
                else:
                    context.on_token(token)

        # Parse sentiments and store in LLM response parsed object directly to be used by next stage
        context.chisa_reply = chisa_reply
        context.citation_ids = citation_ids
        context.estimated_input_tokens = response.input_tokens
        context.estimated_output_tokens = response.output_tokens
        
        # Store parsed sentiment into tool_res for emotion update stage
        sentiment_analysis = response.parsed.get("sentiment") or response.parsed.get("sentiment_analysis", {})
        if not isinstance(sentiment_analysis, dict):
            sentiment_analysis = {}

        user_sentiment = response.parsed.get("user_sentiment", {})
        chisa_sentiment = response.parsed.get("chisa_sentiment", {})
        if not isinstance(user_sentiment, dict):
            user_sentiment = {}
        if not isinstance(chisa_sentiment, dict):
            chisa_sentiment = {}
            
        context.tool_res = context.tool_res or {}
        if grounding is not None:
            context.tool_res["grounding"] = grounding.telemetry()
        elif grounded_envelope is not None and grounded_envelope.abstained:
            context.tool_res["grounding"] = {
                "status": "abstained_insufficient_evidence"
            }
        if grounded_envelope is not None:
            context.tool_res["generation_contract"] = {
                "confidence": grounded_envelope.confidence,
                "safety_flags": grounded_envelope.safety_flags,
                "verified_claims": grounded_envelope.verified_claims,
                "extractive_claims": grounded_envelope.extractive_claims,
                "removed_claims": grounded_envelope.removed_claims,
                "rebound_citations": grounded_envelope.rebound_citations,
                "attachment_ids": grounded_envelope.attachment_ids,
                "abstained": grounded_envelope.abstained,
            }
        context.tool_res["sentiment"] = sentiment_analysis
        context.tool_res["sentiment_analysis"] = sentiment_analysis
        context.tool_res["user_sentiment"] = user_sentiment
        context.tool_res["chisa_sentiment"] = chisa_sentiment

        # Delivery manifests are derived exclusively from retrieved server evidence.
        # Model output is never an attachment source (SEC-06 / FR-RAG-012).
        context.attached_images = resolve_attachment_manifests(context.retrieved_images)

        # Extract visual tags & caption directly from Vision LLM output (0ms added latency auto-tagging)
        if context.has_images:
            raw_tags = response.parsed.get("image_tags") or []
            if isinstance(raw_tags, str):
                raw_tags = [t.strip() for t in raw_tags.split(",") if t.strip()]
            elif isinstance(raw_tags, list):
                raw_tags = [str(t).strip() for t in raw_tags if str(t).strip()]
            else:
                raw_tags = []
            context.image_tags = raw_tags

            raw_caption = response.parsed.get("visual_caption")
            if isinstance(raw_caption, str) and raw_caption.strip():
                context.visual_caption = raw_caption.strip()

        return context

    @staticmethod
    def _requires_grounded_evidence(context: ChatContext) -> bool:
        return any(intent in _GROUNDED_INTENTS for intent in context.intents)

    def _verify_grounding(
        self,
        *,
        context: ChatContext,
        answer: str,
        citation_ids: list[str],
    ):
        if not self._requires_grounded_evidence(context):
            return None
        prompt = context.prompt
        if prompt is None:
            raise RuntimeError("LLMGenerationStage requires a prompt from ContextBuildingStage.")
        return self.claim_evidence_guard.require_supported(
            answer=answer,
            evidence=prompt.retrieved_evidence,
            citation_ids=citation_ids,
        )

    @staticmethod
    async def _abstain_for_missing_evidence(context: ChatContext) -> ChatContext:
        """Return a deterministic limitation instead of asking the model to invent facts."""
        return await LLMGenerationStage._abstain_for_rejected_output(
            context,
            status="abstained_missing_evidence",
        )

    @staticmethod
    async def _abstain_for_rejected_output(
        context: ChatContext,
        *,
        status: str,
    ) -> ChatContext:
        """Deliver a safe limitation after a grounded candidate fails validation."""
        context.chisa_reply = _GROUNDED_ABSTENTION
        context.citation_ids = []
        context.tool_res = context.tool_res or {}
        context.tool_res["grounding"] = {"status": status}
        if context.on_token:
            for token in context.chisa_reply:
                if asyncio.iscoroutinefunction(context.on_token):
                    await context.on_token(token)
                else:
                    context.on_token(token)
        return context
