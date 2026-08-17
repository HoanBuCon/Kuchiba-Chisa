from app.domain.services.chat_pipeline.stage import PipelineStage
from app.domain.services.chat_pipeline.context import ChatContext
from app.domain.services.tool_router import LLMToolRouter
from app.domain.services.intent_classifier import ChatIntent
from app.domain.interfaces.cache_provider import ICacheProvider
from app.domain.interfaces.repositories import IConversationRepository, IEmotionRepository
from app.domain.interfaces.session import IDbSession
from typing import Callable, Awaitable
from app.shared.utils.logger import get_logger
from app.domain.interfaces.tracker import IPipelineTracker

log = get_logger(__name__)

class ToolRoutingStage(PipelineStage):
    """
    Stage 3: Check for System Actions (Tầng 2 - LLM Tool Router)
    """
    def __init__(
        self,
        tool_router: LLMToolRouter,
        cache: ICacheProvider,
        conv_repo_factory: Callable[[IDbSession], IConversationRepository],
        emotion_repo_factory: Callable[[IDbSession], IEmotionRepository],
        pipeline_tracker: IPipelineTracker,
        routing_logger_callback: Callable[..., Awaitable[None]] = None
    ):
        self.tool_router = tool_router
        self.cache = cache
        self.conv_repo_factory = conv_repo_factory
        self.emotion_repo_factory = emotion_repo_factory
        self.pipeline_tracker = pipeline_tracker
        self.routing_logger_callback = routing_logger_callback

    async def process(self, context: ChatContext) -> ChatContext:
        if context.is_cached_answer:
            return context
            
        tool_output_msg = None
        tool_name = "none"
        tool_score = 0.0
        tool_res = None
        
        conv_repo = self.conv_repo_factory(context.session)
        emotion_repo = self.emotion_repo_factory(context.session)

        if ChatIntent.SYSTEM_ACTION in context.intents:
            target_query = context.rewritten_query or context.cleaned_query or context.user_message
            tool_res = await self.tool_router.execute(
                user_message=target_query,
                user_id=context.user_id,
                query_vector=context.query_vector,
                history=context.history,
                conv_repo=conv_repo,
                emotion_repo=emotion_repo,
                cache=self.cache,
                session=context.session
            )
            raw_tool_name = tool_res.get("tool", "none")
            raw_tool_score = tool_res.get("score", 0.0)

            # If tool selected is web_search, delegate to RAGStage / ThinkingLoopAgent to prevent duplicate search
            if raw_tool_name == "web_search":
                log.info("ToolRouter identified web_search; delegating to RAGStage ThinkingLoop for unified iterative retrieval")
                tool_output_msg = None
                tool_name = "none"
                tool_score = 0.0
                context.needs_web_search = True
            else:
                tool_output_msg = tool_res.get("message")
                tool_name = raw_tool_name
                tool_score = raw_tool_score
                log.info("Tool executed from SYSTEM_ACTION intent", tool_res=tool_res, query=target_query)

        intent_values = [i.value for i in context.intents]

        # Log Semantic Routing & Tool Decisions
        if self.routing_logger_callback:
            await self.routing_logger_callback(
                user_message=context.user_message,
                is_small_talk=context.is_small_talk,
                intents=intent_values,
                tool_name=tool_name,
                tool_score=tool_score,
                tool_result=tool_output_msg or ""
            )

        reason_text = (
            f"Đã kích hoạt công cụ '{tool_name}' với độ tin cậy {round(tool_score * 100)}%."
            if tool_name != "none"
            else "Không kích hoạt công cụ ngoài (Chuyển tiếp RAG Pipeline & Tri thức)."
        )

        self.pipeline_tracker.add_step("tool_routing", {
            "tool_name": tool_name,
            "selected_tool": tool_name,
            "tool_score": tool_score,
            "confidence": tool_score,
            "tool_result": tool_output_msg or "",
            "tool_output": tool_output_msg or "",
            "reason": reason_text,
            "status": "success" if tool_name != "none" else "skipped"
        })

        if tool_name == "web_search" and tool_res:
            from app.domain.services.tools.web_search import web_search_trace_payload
            self.pipeline_tracker.add_step(
                "web_search",
                web_search_trace_payload(
                    tool_res,
                    source="tool_routing",
                    original_message=context.user_message,
                ),
            )

        context.tool_output_msg = tool_output_msg
        context.tool_name = tool_name
        context.tool_score = tool_score
        context.tool_res = tool_res

        return context
