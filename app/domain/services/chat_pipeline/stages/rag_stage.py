from app.domain.services.chat_pipeline.stage import PipelineStage
from app.domain.services.chat_pipeline.context import ChatContext
from app.domain.services.rag.pipeline import RAGPipeline
from app.domain.interfaces.llm_provider import BaseLLMAdapter
from app.domain.interfaces.embedding_provider import IEmbeddingProvider
from app.domain.interfaces.vector_store import IVectorStore
from app.domain.services.tool_router import LLMToolRouter

class RAGStage(PipelineStage):
    """
    Stage 4: E2E RAG Pipeline (Retrieval, Context Assessment, and Loop Thinking)
    """
    def __init__(
        self,
        llm: BaseLLMAdapter,
        embedder: IEmbeddingProvider,
        vector_store: IVectorStore,
        tool_router: LLMToolRouter,
        rag_pipeline: RAGPipeline
    ):
        self.llm = llm
        self.embedder = embedder
        self.vector_store = vector_store
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
            cleaned_query=context.cleaned_query,
            intents=context.intents,
            current_emotions=context.current_emotions,
            history=context.history,
            llm=self.llm,
            embedder=self.embedder,
            web_search_tool=self.tool_router.tool_map.get("web_search"),
            is_small_talk=context.is_small_talk,
            conversation_summary=context.conversation_summary,
        )
        
        context.rag_context = rag_context
        
        # If the RAG process yielded a tool output message, we can override or merge it.
        # Following the old ChatEngine logic:
        # tool_output_msg = rag_context.tool_output_msg (which overrides previous)
        if rag_context.tool_output_msg:
            context.tool_output_msg = rag_context.tool_output_msg

        return context
