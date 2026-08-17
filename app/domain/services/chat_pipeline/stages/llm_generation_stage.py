import asyncio
from typing import Dict, Any, Callable, Awaitable
from app.domain.services.chat_pipeline.stage import PipelineStage
from app.domain.services.chat_pipeline.context import ChatContext
from app.domain.interfaces.llm_provider import BaseLLMAdapter, LLMResponse, StructuredPrompt
from app.shared.utils.json_stream_parser import IncrementalJsonParser
from app.shared.utils.token_estimator import TokenEstimator
from app.shared.utils.logger import get_logger
from app.config.settings import settings
from app.domain.context import llm_call_purpose

log = get_logger(__name__)

class LLMGenerationStage(PipelineStage):
    """
    Stage 6: LLM Generation (streaming or non-streaming) and token control.
    """
    def __init__(self, llm: BaseLLMAdapter, llm_logger_callback: Callable[[StructuredPrompt, LLMResponse], Awaitable[None]] = None):
        self.llm = llm
        self.llm_logger_callback = llm_logger_callback

    async def process(self, context: ChatContext) -> ChatContext:
        if context.is_cached_answer:
            if context.on_token and context.response_text:
                for token in context.response_text:
                    if asyncio.iscoroutinefunction(context.on_token):
                        await context.on_token(token)
                    else:
                        context.on_token(token)
            return context
            
        log.info("Generating response with structured LLM")
        llm_call_purpose.set("chat_response")
        
        if context.on_token:
            parser = IncrementalJsonParser()
            raw_chunks = []
            raw_response = ""
            parsed = {}
            error_to_raise = None
            
            try:
                async for chunk in self.llm.stream(context.prompt):
                    raw_chunks.append(chunk)
                    parsed_token = parser.feed(chunk)
                    if parsed_token:
                        if asyncio.iscoroutinefunction(context.on_token):
                            await context.on_token(parsed_token)
                        else:
                            context.on_token(parsed_token)
                
                raw_response = "".join(raw_chunks)
                parsed = await self.llm.validate_response(raw_response, context.prompt.response_schema)
            except Exception as e:
                error_to_raise = e
            
            est_input = (
                TokenEstimator.estimate(context.prompt.system)
                + TokenEstimator.estimate_messages(context.prompt.history)
                + TokenEstimator.estimate(context.prompt.user_message)
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
                model=self.llm._model,
                finish_reason="stop",
                reasoning_content=reasoning_content,
            )

            try:
                if self.llm_logger_callback:
                    await self.llm_logger_callback(context.prompt, response)
            except Exception as log_ex:
                log.warning("Failed to log streaming transaction", error=str(log_ex))
                
            if error_to_raise:
                raise error_to_raise
        else:
            response = await self.llm.generate(context.prompt)

        chisa_reply = response.parsed.get("response")
        
        # Fallback if parsing has mismatched JSON key but correct raw JSON string
        if not chisa_reply and response.parsed:
            for val in response.parsed.values():
                if isinstance(val, str) and val.strip():
                    chisa_reply = val
                    break
                    
        chisa_reply = chisa_reply or ""
        
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

        # Parse sentiments and store in LLM response parsed object directly to be used by next stage
        context.chisa_reply = chisa_reply
        context.estimated_input_tokens = response.input_tokens
        context.estimated_output_tokens = response.output_tokens
        
        # Store parsed sentiment into tool_res for emotion update stage
        sentiment_analysis = response.parsed.get("sentiment_analysis", {})
        if not isinstance(sentiment_analysis, dict):
            sentiment_analysis = {}

        user_sentiment = response.parsed.get("user_sentiment", {})
        chisa_sentiment = response.parsed.get("chisa_sentiment", {})
        if not isinstance(user_sentiment, dict):
            user_sentiment = {}
        if not isinstance(chisa_sentiment, dict):
            chisa_sentiment = {}
            
        context.tool_res = context.tool_res or {}
        context.tool_res["sentiment_analysis"] = sentiment_analysis
        context.tool_res["user_sentiment"] = user_sentiment
        context.tool_res["chisa_sentiment"] = chisa_sentiment

        return context
