"""Publish only deliverable, grounded final lore answers to Redis."""

from __future__ import annotations

from collections.abc import Callable
from time import time

from app.domain.interfaces.cache_provider import ICacheProvider
from app.domain.interfaces.lore_corpus_identity import ILoreCorpusIdentityProvider
from app.domain.services.chat_pipeline.context import ChatContext
from app.domain.services.chat_pipeline.stage import PipelineStage
from app.domain.services.lore_answer_cache import LoreAnswerCacheContract
from app.shared.utils.logger import get_logger

log = get_logger(__name__)


class CacheUpdateStage(PipelineStage):
    def __init__(
        self,
        cache: ICacheProvider,
        corpus_identity_provider: ILoreCorpusIdentityProvider,
        contract: LoreAnswerCacheContract,
        clock: Callable[[], float] = time,
    ) -> None:
        self.cache = cache
        self.corpus_identity_provider = corpus_identity_provider
        self.contract = contract
        self.clock = clock

    async def process(self, context: ChatContext) -> ChatContext:
        identity = context.lore_cache_identity
        if identity is None or not self.contract.request_is_eligible(context):
            return context
        try:
            current_corpus = await self.corpus_identity_provider.active_lore_corpus_identity()
        except Exception as error:
            context.lore_cache_outcome = "write_unavailable"
            log.warning(
                "Lore cache corpus revalidation unavailable",
                error_type=type(error).__name__,
            )
            return context
        if current_corpus is None:
            context.lore_cache_outcome = "write_unavailable"
            return context
        current_identity = self.contract.identity(context, current_corpus)
        if current_identity.digest != identity.digest:
            context.lore_cache_outcome = "stale_version"
            return context
        entry = self.contract.build_entry(context, identity, now=self.clock())
        if entry is None:
            context.lore_cache_outcome = "not_cacheable"
            return context
        try:
            await self.cache.set(
                identity.key,
                entry.model_dump_json(),
                ttl=self.contract.policy.ttl_seconds,
            )
        except Exception as error:
            context.lore_cache_outcome = "write_unavailable"
            log.warning("Lore answer cache write unavailable", error_type=type(error).__name__)
            return context
        context.lore_cache_outcome = "write"
        log.info("Saved grounded lore answer", cache_identity=identity.digest[:12])
        return context
