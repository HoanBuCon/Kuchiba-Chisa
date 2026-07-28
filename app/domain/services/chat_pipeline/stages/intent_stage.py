from app.domain.services.chat_pipeline.stage import PipelineStage
from app.domain.services.chat_pipeline.context import ChatContext
from app.domain.services.intent_classifier import IntentClassifier, ChatIntent
from app.domain.interfaces.embedding_provider import IEmbeddingProvider
from app.shared.utils.query_cleaner import clean_query_for_rag
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
        if not is_st:
            cleaned_query = clean_query_for_rag(context.user_message)
            
        intents, query_vector = await self.intent_classifier.classify(context.user_message, query_vector)
        intent_values = [i.value for i in intents]

        # If query_vector is not generated yet and query is not small talk, embed now for RAG/fallback retrieval
        if not is_st and query_vector is None:
            query_vector = await self.embedder.embed_text(cleaned_query)
                
        log.info("Production query classified", intents=intent_values, user_id=context.user_id)

        if self.pipeline_tracker:
            self.pipeline_tracker.add_step("intent_classification", {
                "is_small_talk": is_st,
                "intents": intent_values,
                "cleaned_query": cleaned_query
            })

        context.is_small_talk = is_st
        context.cleaned_query = cleaned_query
        context.query_vector = query_vector
        context.intents = intents

        return context
