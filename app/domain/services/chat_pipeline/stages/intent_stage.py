from typing import Optional
from app.domain.services.chat_pipeline.stage import PipelineStage
from app.domain.services.chat_pipeline.context import ChatContext
from app.domain.models.intent_result import IntentResult, ChatIntent
from app.domain.services.intent_classifier import IntentClassifier
from app.domain.interfaces.embedding_provider import IEmbeddingProvider
from app.shared.utils.query_cleaner import clean_query_for_rag, is_meaningful_query
from app.shared.utils.logger import get_logger
from app.domain.interfaces.tracker import IPipelineTracker

log = get_logger(__name__)

class IntentStage(PipelineStage):
    """
    Stage 2: Classify intent, clean query, and embed the query vector if needed.
    """
    def __init__(self, intent_classifier: IntentClassifier, embedder: IEmbeddingProvider, pipeline_tracker: IPipelineTracker = None):
        self.intent_classifier = intent_classifier
        self.embedder = embedder
        self.pipeline_tracker = pipeline_tracker

    async def process(self, context: ChatContext) -> ChatContext:
        is_st = IntentClassifier.is_small_talk(context.user_message)
        
        query_vector = None
        cleaned_query = ""
        intent_result: Optional[IntentResult] = None

        if not is_st:
            cleaned_query = clean_query_for_rag(context.user_message)
            # Second-level guard: If cleaned query contains no meaningful search content (e.g. only "em", "chisa"), treat as small talk!
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
                routing_reason="L1 Small Talk regex/post-clean guard matched (Bỏ qua RAG)"
            )
        else:
            # Embed cleaned_query consistently to ensure vector alignment with RAG
            query_vector = await self.embedder.embed_text(cleaned_query)
            intent_result = await self.intent_classifier.classify(cleaned_query, query_vector)

        intent_values = [i.value for i in intent_result.intents]
        log.info(
            "Production query classified",
            intents=intent_values,
            confidence=intent_result.confidence,
            method=intent_result.routing_method,
            user_id=context.user_id
        )

        context.intent_result = intent_result
        context.cleaned_query = cleaned_query
        context.query_vector = intent_result.query_vector or query_vector
        context.intents = intent_result.intents

        if self.pipeline_tracker:
            self.pipeline_tracker.add_step("intent_classification", {
                "is_small_talk": context.is_small_talk,
                "intents": intent_values,
                "cleaned_query": cleaned_query,
                "confidence": intent_result.confidence,
                "routing_method": intent_result.routing_method,
                "semantic_scores": intent_result.semantic_scores,
                "rag_triggered": not context.is_small_talk,
                "routing_reason": intent_result.routing_reason
            })

        return context
