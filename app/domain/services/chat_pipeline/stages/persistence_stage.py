import time
from collections.abc import Callable

from app.domain.interfaces.cache_provider import ICacheProvider
from app.domain.interfaces.repositories import IConversationRepository, IUserRepository
from app.domain.interfaces.session import IDbSession
from app.domain.interfaces.tracker import IPipelineTracker
from app.domain.services.chat_pipeline.context import ChatContext
from app.domain.services.chat_pipeline.stage import PipelineStage


class PersistenceStage(PipelineStage):
    """
    Stage 9: Save messages to Postgres and update user stats with Redis Write-Through State Cache.
    """

    def __init__(
        self,
        user_repo_factory: Callable[[IDbSession], IUserRepository],
        conv_repo_factory: Callable[[IDbSession], IConversationRepository],
        cache_provider: ICacheProvider | None = None,
        pipeline_tracker: IPipelineTracker | None = None,
    ):
        self.user_repo_factory = user_repo_factory
        self.conv_repo_factory = conv_repo_factory
        self.cache_provider = cache_provider
        self.pipeline_tracker = pipeline_tracker

    async def process(self, context: ChatContext) -> ChatContext:
        user_uuid = context.user_uuid
        conversation_id = context.conv_id
        stats = context.stats
        if user_uuid is None or conversation_id is None or stats is None:
            raise RuntimeError(
                "PersistenceStage requires initialized user, conversation, and stats."
            )

        user_repo = self.user_repo_factory(context.session)
        conv_repo = self.conv_repo_factory(context.session)

        total_tokens = context.estimated_input_tokens + context.estimated_output_tokens
        user_rw = context.rewritten_query or context.cleaned_query or None

        media_meta = None
        if context.processed_images and not context.is_ephemeral_reference:
            media_meta = [
                {
                    "image_id": img.get("image_id"),
                    "url": img.get("url"),
                    "thumbnail_url": img.get("thumbnail_url"),
                    "width": img.get("width"),
                    "height": img.get("height"),
                    "size_bytes": img.get("size_bytes"),
                    "is_ephemeral": img.get("is_ephemeral"),
                }
                for img in context.processed_images
            ]

        await conv_repo.save_message(
            conversation_id,
            user_uuid,
            "user",
            context.user_message,
            rewritten_content=user_rw,
            is_success=True,
            media_metadata=media_meta,
        )
        await conv_repo.save_message(
            conversation_id,
            user_uuid,
            "assistant",
            context.chisa_reply,
            token_count=total_tokens,
            is_success=True,
        )

        stats.interaction_count += 1
        stats.last_seen = int(time.time() * 1000)
        await user_repo.update_stats(stats)

        # Write-Through to Redis State Cache
        if self.cache_provider and context.emotion:
            from app.domain.services.user_state_cache import UserStateCache

            await UserStateCache.set_state(
                self.cache_provider, user_uuid, stats, context.emotion, conversation_id
            )

        if self.pipeline_tracker:
            self.pipeline_tracker.add_step(
                name="persistence",
                stage_id="stage_9_persist",
                depth=0,
                category="stage_root",
                status="success",
                title="Stage 9: [PERSIST] Lưu trữ Dữ liệu Bền vững",
                subtitle=f"Interaction #{stats.interaction_count} · {total_tokens} tokens",
                data={
                    "conv_id": str(conversation_id),
                    "user_uuid": user_uuid,
                    "user_message_length": len(context.user_message) if context.user_message else 0,
                    "assistant_reply_length": len(context.chisa_reply)
                    if context.chisa_reply
                    else 0,
                    "interaction_count": stats.interaction_count,
                    "last_seen": stats.last_seen,
                    "total_tokens_persisted": total_tokens,
                    "status": "success",
                },
            )

        return context
