from typing import Callable, Optional
from app.domain.interfaces.session import IDbSession
from app.domain.services.chat_pipeline.stage import PipelineStage
from app.domain.services.chat_pipeline.context import ChatContext
from app.domain.services.emotion_engine import EmotionEngine
from app.domain.interfaces.repositories import IEmotionRepository
from app.domain.interfaces.cache_provider import ICacheProvider
from app.domain.interfaces.tracker import IPipelineTracker

class EmotionUpdateStage(PipelineStage):
    """
    Stage 8: Update individual emotion state based on sentiments and
    sync collective Server-Level Ambient State in shared environments.
    """
    def __init__(
        self,
        emotion_engine: EmotionEngine,
        emotion_repo_factory: Callable[[IDbSession], IEmotionRepository],
        cache_provider: Optional[ICacheProvider] = None,
        pipeline_tracker: IPipelineTracker = None
    ):
        self.emotion_engine = emotion_engine
        self.emotion_repo_factory = emotion_repo_factory
        self.cache_provider = cache_provider
        self.pipeline_tracker = pipeline_tracker

    async def process(self, context: ChatContext) -> ChatContext:
        tool_res = context.tool_res or {}
        sentiment_analysis = tool_res.get("sentiment") or tool_res.get("sentiment_analysis", {})
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

        # Sync Server-Level Ambient Mood in shared server environments
        is_server_shared = (
            bool(context.guild_id)
            and not context.guild_id.startswith("CHANNEL_")
            and context.guild_id != "DM"
        )
        if is_server_shared and self.cache_provider:
            from app.domain.services.community.ambient_manager import AmbientMoodManager
            ambient_snapshot = AmbientMoodManager.extract_ambient_snapshot(context.emotion)
            cache_key = f"chisa:guild:{context.guild_id}:ambient_mood"
            await self.cache_provider.set_json(cache_key, ambient_snapshot, ttl=7200)

        if self.pipeline_tracker:
            self.pipeline_tracker.add_step("emotion_update", {
                "old_emotions": context.current_emotions,
                "new_emotions": {
                    "joy": context.emotion.joy,
                    "sadness": context.emotion.sadness,
                    "trust": context.emotion.trust,
                    "irritation": context.emotion.irritation,
                    "attachment": context.emotion.attachment,
                    "shyness": getattr(context.emotion, "shyness", 0.0),
                    "curiosity": getattr(context.emotion, "curiosity", 0.20),
                    "comfort": getattr(context.emotion, "comfort", 0.50),
                },
                "delta": {
                    "joy": delta.joy_delta,
                    "sadness": delta.sadness_delta,
                    "trust": delta.trust_delta,
                    "irritation": delta.irritation_delta,
                    "attachment": delta.attachment_delta,
                    "shyness": delta.shyness_delta,
                    "curiosity": delta.curiosity_delta,
                    "comfort": delta.comfort_delta,
                },
                "server_ambient_synced": is_server_shared,
                "sentiment": {
                    "reaction": delta.reaction,
                    "user_stance": delta.user_stance,
                    "intensity": delta.intensity,
                    "variance": delta.variance,
                },
                "sentiment_analysis": {
                    "primary_emotion": delta.primary_emotion,
                    "intensity": delta.intensity,
                    "valence": delta.valence,
                    "reaction": delta.reaction,
                    "user_stance": delta.user_stance,
                    "variance": delta.variance,
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

        context.updated_emotions = {
            "joy": context.emotion.joy,
            "sadness": context.emotion.sadness,
            "trust": context.emotion.trust,
            "irritation": context.emotion.irritation,
            "attachment": context.emotion.attachment,
            "shyness": getattr(context.emotion, "shyness", 0.0),
            "curiosity": getattr(context.emotion, "curiosity", 0.20),
            "comfort": getattr(context.emotion, "comfort", 0.50),
        }

        return context
