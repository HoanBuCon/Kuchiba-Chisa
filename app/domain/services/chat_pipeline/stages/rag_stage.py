from app.domain.services.chat_pipeline.stage import PipelineStage
from app.domain.services.chat_pipeline.context import ChatContext
from app.domain.services.rag.pipeline import RAGPipeline
from app.domain.interfaces.llm_provider import BaseLLMAdapter
from app.domain.interfaces.embedding_provider import IEmbeddingProvider
from app.domain.services.tool_router import LLMToolRouter

class RAGStage(PipelineStage):
    """
    Stage 4: E2E RAG Pipeline (Retrieval, Context Assessment, and Loop Thinking)
    """
    def __init__(
        self,
        llm: BaseLLMAdapter,
        embedder: IEmbeddingProvider,
        tool_router: LLMToolRouter,
        rag_pipeline: RAGPipeline
    ):
        self.llm = llm
        self.embedder = embedder
        self.tool_router = tool_router
        self.rag_pipeline = rag_pipeline

    async def process(self, context: ChatContext) -> ChatContext:
        if context.is_cached_answer:
            return context

        rag_context = await self.rag_pipeline.retrieve_and_align(
            session=context.session,
            user_id=context.user_id,
            user_message=context.user_message,
            query_vector=context.query_vector,
            cleaned_query=context.rewritten_query or context.cleaned_query,
            intents=context.intents,
            current_emotions=context.current_emotions,
            history=context.history,
            llm=self.llm,
            embedder=self.embedder,
            web_search_tool=self.tool_router.tool_map.get("web_search"),
            is_small_talk=context.is_small_talk,
            conversation_summary=context.conversation_summary,
            conversation_id=str(context.conv_id) if context.conv_id else None,
            guild_id=context.guild_id,
            channel_id=context.channel_id,
            needs_vector_search=context.needs_vector_search,
            needs_web_search=context.needs_web_search,
        )
        
        context.rag_context = rag_context
        context.retrieved_images = getattr(rag_context, "retrieved_images", [])
        
        # If the RAG process yielded a tool output message, we can override or merge it.
        # Following the old ChatEngine logic:
        # tool_output_msg = rag_context.tool_output_msg (which overrides previous)
        if rag_context.tool_output_msg:
            context.tool_output_msg = rag_context.tool_output_msg

        return context
