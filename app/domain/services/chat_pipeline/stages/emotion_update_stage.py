from typing import Callable
from app.domain.interfaces.session import IDbSession
from app.domain.services.chat_pipeline.stage import PipelineStage
from app.domain.services.chat_pipeline.context import ChatContext
from app.domain.services.emotion_engine import EmotionEngine
from app.domain.interfaces.repositories import IEmotionRepository
from app.domain.interfaces.tracker import IPipelineTracker

class EmotionUpdateStage(PipelineStage):
    """
    Stage 7: Update emotion state based on sentiments.
    """
    def __init__(
        self,
        emotion_engine: EmotionEngine,
        emotion_repo_factory: Callable[[IDbSession], IEmotionRepository],
        pipeline_tracker: IPipelineTracker = None
    ):
        self.emotion_engine = emotion_engine
        self.emotion_repo_factory = emotion_repo_factory
        self.pipeline_tracker = pipeline_tracker

    async def process(self, context: ChatContext) -> ChatContext:
        tool_res = context.tool_res or {}
        sentiment_analysis = tool_res.get("sentiment_analysis", {})
        user_sentiment = tool_res.get("user_sentiment", {})
        chisa_sentiment = tool_res.get("chisa_sentiment", {})
        
        is_positive = user_sentiment.get("is_positive", False)
        is_negative = user_sentiment.get("is_negative", False)
        is_rude = user_sentiment.get("is_rude", False)
        is_neutral = user_sentiment.get("is_neutral", True)
        
        chisa_sad = chisa_sentiment.get("is_sad", False)
        chisa_happy = chisa_sentiment.get("is_happy", False)
        chisa_annoyed = chisa_sentiment.get("is_annoyed", False)
        chisa_flustered = chisa_sentiment.get("is_flustered", False)
        
        emotion_repo = self.emotion_repo_factory(context.session)

        delta = self.emotion_engine.update(
            context.emotion,
            sentiment_analysis=sentiment_analysis,
            is_positive=is_positive,
            is_negative=is_negative,
            is_rude=is_rude,
            is_neutral=is_neutral,
            chisa_sad=chisa_sad,
            chisa_happy=chisa_happy,
            chisa_annoyed=chisa_annoyed,
            chisa_flustered=chisa_flustered
        )
        await emotion_repo.update_emotion(context.emotion)

        if self.pipeline_tracker:
            self.pipeline_tracker.add_step("emotion_update", {
                "old_emotions": context.current_emotions,
                "new_emotions": {
                    "joy": context.emotion.joy,
                    "sadness": context.emotion.sadness,
                    "trust": context.emotion.trust,
                    "irritation": context.emotion.irritation,
                    "attachment": context.emotion.attachment + context.attachment_bonus_raw,
                    "shyness": getattr(context.emotion, "shyness", 0.0),
                    "curiosity": getattr(context.emotion, "curiosity", 0.20),
                    "comfort": getattr(context.emotion, "comfort", 0.50),
                },
                "sentiment_analysis": {
                    "primary_emotion": delta.primary_emotion,
                    "intensity": delta.intensity,
                    "valence": delta.valence,
                },
                "user_sentiment": {
                    "is_positive": is_positive,
                    "is_negative": is_negative,
                    "is_rude": is_rude,
                    "is_neutral": is_neutral
                },
                "chisa_sentiment": {
                    "is_sad": chisa_sad,
                    "is_happy": chisa_happy,
                    "is_annoyed": chisa_annoyed,
                    "is_flustered": chisa_flustered
                }
            })

        # Recompute dampening details for return
        attachment_bonus = context.attachment_bonus_raw
        if context.emotion.sadness > 0.15 and context.emotion.irritation > 0.10:
            dampen_factor = max(0.0, 1.0 - (context.emotion.sadness * context.emotion.irritation * 3.0))
            attachment_bonus = context.attachment_bonus_raw * dampen_factor
            
        context.updated_emotions = {
            "joy": context.emotion.joy,
            "sadness": context.emotion.sadness,
            "trust": context.emotion.trust,
            "irritation": context.emotion.irritation,
            "attachment": context.emotion.attachment + attachment_bonus,
            "shyness": getattr(context.emotion, "shyness", 0.0),
            "curiosity": getattr(context.emotion, "curiosity", 0.20),
            "comfort": getattr(context.emotion, "comfort", 0.50),
        }

        return context
