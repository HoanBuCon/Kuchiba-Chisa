from typing import Callable, Optional
from app.domain.services.chat_pipeline.stage import PipelineStage
from app.domain.services.chat_pipeline.context import ChatContext
from app.domain.models.intent_result import IntentResult, ChatIntent
from app.domain.services.intent_classifier import IntentClassifier
from app.domain.services.rag.query_rewriter import QueryRewriter
from app.domain.interfaces.embedding_provider import IEmbeddingProvider
from app.domain.interfaces.session import IDbSession
from app.domain.interfaces.repositories import IConversationRepository
from app.shared.utils.query_cleaner import clean_query_for_rag, is_meaningful_query
from app.shared.utils.logger import get_logger
from app.domain.interfaces.tracker import IPipelineTracker

log = get_logger(__name__)

class IntentStage(PipelineStage):
    """
    Stage 2: Classify intent, perform Tiered Query Rewrite (Fast-Path / Micro LLM Rewrite),
    and embed the final aligned query vector for RAG.
    """
    def __init__(
        self,
        intent_classifier: IntentClassifier,
        embedder: IEmbeddingProvider,
        query_rewriter: Optional[QueryRewriter] = None,
        conv_repo_factory: Optional[Callable[[IDbSession], IConversationRepository]] = None,
        pipeline_tracker: Optional[IPipelineTracker] = None,
    ):
        self.intent_classifier = intent_classifier
        self.embedder = embedder
        self.query_rewriter = query_rewriter
        self.conv_repo_factory = conv_repo_factory
        self.pipeline_tracker = pipeline_tracker

    async def process(self, context: ChatContext) -> ChatContext:
        is_st = IntentClassifier.is_small_talk(context.user_message)
        
        query_vector = None
        cleaned_query = ""
        rewritten_query = ""
        rewrite_method = "FAST_PATH"
        intent_result: Optional[IntentResult] = None

        if not is_st:
            cleaned_query = clean_query_for_rag(context.user_message)
            # Second-level guard: If cleaned query contains no meaningful search content, treat as small talk!
            if not is_meaningful_query(cleaned_query):
                log.info("Intent post-clean guard: query cleaned down to non-meaningful content", original=context.user_message, cleaned=cleaned_query)
                is_st = True
                cleaned_query = ""

        if is_st:
            intent_result = IntentResult(
                intents=[ChatIntent.SMALL_TALK],
                confidence=1.0,
                routing_method="L1_SMALL_TALK",
                query_vector=None,
                semantic_scores={"SMALL_TALK": 1.0},
                routing_reason="L1 Small Talk fast-path matched (Bypass RAG & Rewrite)"
            )
            rewritten_query = context.user_message
            rewrite_method = "BYPASS"
        else:
            # 1. Preliminary classification on cleaned_query
            prelim_vec = await self.embedder.embed_text(cleaned_query, prefix="query: ")
            intent_result = await self.intent_classifier.classify(cleaned_query, prelim_vec)

            # 2. Retrieve previous user rewritten query from SQL (1-Turn Context Chaining)
            prev_rewritten_query = None
            if self.conv_repo_factory and context.session and context.conv_id and context.user_uuid:
                try:
                    conv_repo = self.conv_repo_factory(context.session)
                    prev_rewritten_query = await conv_repo.get_last_user_rewritten_query(
                        user_id=context.user_uuid,
                        conversation_id=context.conv_id
                    )
                except Exception as e:
                    log.warning("Failed to fetch last rewritten query from SQL", error=str(e))

            # Fallback to history if SQL didn't have it
            if not prev_rewritten_query and context.history:
                user_hist = [h["content"] for h in context.history if h.get("role") == "user"]
                if user_hist:
                    prev_rewritten_query = user_hist[-1]

            # 3. Dual-Signal Decision Matrix
            has_history = bool(prev_rewritten_query or context.history)
            decision_info = IntentClassifier.determine_routing_and_rewrite(
                user_message=context.user_message,
                cleaned_query=cleaned_query,
                intent_result=intent_result,
                has_history=has_history
            )

            rewrite_decision = decision_info["decision"]

            # 4. Execute Tiered Rewrite
            if self.query_rewriter:
                rewritten_query, rewrite_method = await self.query_rewriter.rewrite(
                    user_message=context.user_message,
                    cleaned_query=cleaned_query,
                    prev_rewritten_query=prev_rewritten_query,
                    needs_llm_rewrite=(rewrite_decision == "LLM_REWRITE"),
                )
            else:
                # Fast-Path: Zero-token entity alias enrichment
                if self.intent_classifier.entity_resolver:
                    from app.domain.services.rag.entity_resolver import enrich_query_with_entities
                    rewritten_query = enrich_query_with_entities(cleaned_query, self.intent_classifier.entity_resolver)
                else:
                    rewritten_query = cleaned_query
                rewrite_method = "FAST_PATH"

            # 5. Embed the final aligned query for RAG
            if rewritten_query != cleaned_query:
                query_vector = await self.embedder.embed_text(rewritten_query, prefix="query: ")
                # Re-check intent if rewritten query significantly changed
                intent_result.query_vector = query_vector
            else:
                query_vector = prelim_vec

        intent_values = [i.value for i in intent_result.intents]
        log.info(
            "Production query classified and routed",
            intents=intent_values,
            confidence=intent_result.confidence,
            method=intent_result.routing_method,
            rewrite_method=rewrite_method,
            rewritten_query=rewritten_query,
            user_id=context.user_id
        )

        context.intent_result = intent_result
        context.cleaned_query = cleaned_query
        context.rewritten_query = rewritten_query
        context.rewrite_method = rewrite_method
        context.query_vector = query_vector
        context.intents = intent_result.intents

        if self.pipeline_tracker:
            self.pipeline_tracker.add_step("intent_classification", {
                "is_small_talk": context.is_small_talk,
                "intents": intent_values,
                "cleaned_query": cleaned_query,
                "rewritten_query": rewritten_query,
                "rewrite_method": rewrite_method,
                "confidence": intent_result.confidence,
                "routing_method": intent_result.routing_method,
                "semantic_scores": intent_result.semantic_scores,
                "rag_triggered": not context.is_small_talk,
                "routing_reason": intent_result.routing_reason
            })

        return context
