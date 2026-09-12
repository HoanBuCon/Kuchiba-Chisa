"""Typed correctness contract for final lore-answer caching (TD-025)."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.domain.interfaces.lore_corpus_identity import LoreCorpusIdentity
from app.domain.models.evidence import Evidence, EvidenceAccess
from app.domain.models.intent_result import ChatIntent

if TYPE_CHECKING:
    from app.domain.services.chat_pipeline.context import ChatContext


CACHE_SCHEMA_VERSION = "lore-answer-v2"
ANSWER_SCHEMA_VERSION = "submit-grounded-answer-v1"
CACHE_KEY_PREFIX = f"chisa:answer_cache:lore:{CACHE_SCHEMA_VERSION}"
_SPACE = re.compile(r"\s+")


def _fingerprint(value: object) -> str:
    canonical = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class LoreAnswerCachePolicy:
    """Explicit semantic versions supplied at the composition boundary."""

    generation_fingerprint: str
    prompt_semantics_version: str
    grounding_contract_version: str
    ttl_seconds: int = 86_400


@dataclass(frozen=True, slots=True)
class LoreAnswerCacheIdentity:
    digest: str
    key: str
    corpus_fingerprint: str
    generation_fingerprint: str
    prompt_fingerprint: str
    grounding_contract_version: str
    authorization_fingerprint: str


class CachedCitation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_id: str = Field(min_length=1, max_length=512)
    access_scope: Literal["public", "user", "tenant"]
    access_binding_fingerprint: str = Field(min_length=64, max_length=64)


class LoreAnswerCacheEntry(BaseModel):
    """Versioned Redis value; incompatible values are never partially reused."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["lore-answer-v2"] = "lore-answer-v2"
    identity_digest: str = Field(min_length=64, max_length=64)
    corpus_fingerprint: str = Field(min_length=64, max_length=64)
    generation_fingerprint: str = Field(min_length=64, max_length=64)
    prompt_fingerprint: str = Field(min_length=64, max_length=64)
    grounding_contract_version: str = Field(min_length=1, max_length=128)
    authorization_fingerprint: str = Field(min_length=64, max_length=64)
    answer: str = Field(min_length=1)
    citations: tuple[CachedCitation, ...] = Field(min_length=1)
    grounding_status: Literal["verified"] = "verified"
    created_at: float
    expires_at: float


class LoreAnswerCacheContract:
    """Pure policy: identity, eligibility and cache-entry validation."""

    def __init__(self, policy: LoreAnswerCachePolicy) -> None:
        if policy.ttl_seconds <= 0:
            raise ValueError("lore answer cache TTL must be positive")
        if not re.fullmatch(r"[0-9a-f]{64}", policy.generation_fingerprint):
            raise ValueError("generation fingerprint must be a SHA-256 hex digest")
        self.policy = policy

    @staticmethod
    def request_is_eligible(context: ChatContext) -> bool:
        intents = set(context.intents)
        return bool(
            ChatIntent.LORE in intents
            and intents.issubset({ChatIntent.LORE, ChatIntent.KNOWLEDGE_OR_TASK})
            and not context.is_small_talk
            and not context.has_images
            and not context.needs_web_search
            and not context.tool_output_msg
            and (context.rewritten_query or context.cleaned_query).strip()
        )

    def identity(
        self, context: ChatContext, corpus: LoreCorpusIdentity
    ) -> LoreAnswerCacheIdentity:
        normalized_query = _SPACE.sub(
            " ", (context.rewritten_query or context.cleaned_query).strip().casefold()
        )
        corpus_fingerprint = _fingerprint(corpus.alias_targets)
        authorization_fingerprint = self._authorization_fingerprint(context)
        prompt_fingerprint = _fingerprint(
            {
                "version": self.policy.prompt_semantics_version,
                "context": self._prompt_context(context),
            }
        )
        components = {
            "schema": CACHE_SCHEMA_VERSION,
            "query": _fingerprint(normalized_query),
            "corpus": corpus_fingerprint,
            "generation": self.policy.generation_fingerprint,
            "answer_schema": ANSWER_SCHEMA_VERSION,
            "prompt": prompt_fingerprint,
            "grounding": self.policy.grounding_contract_version,
            "authorization": authorization_fingerprint,
        }
        digest = _fingerprint(components)
        return LoreAnswerCacheIdentity(
            digest=digest,
            key=f"{CACHE_KEY_PREFIX}:{digest}",
            corpus_fingerprint=corpus_fingerprint,
            generation_fingerprint=self.policy.generation_fingerprint,
            prompt_fingerprint=prompt_fingerprint,
            grounding_contract_version=self.policy.grounding_contract_version,
            authorization_fingerprint=authorization_fingerprint,
        )

    def build_entry(
        self,
        context: ChatContext,
        identity: LoreAnswerCacheIdentity,
        *,
        now: float,
    ) -> LoreAnswerCacheEntry | None:
        if not self.result_is_cacheable(context):
            return None
        assert context.prompt is not None
        evidence_by_id = {item.evidence_id: item for item in context.prompt.retrieved_evidence}
        citations = tuple(
            self._citation(item=evidence_by_id[citation_id])
            for citation_id in context.citation_ids
        )
        return LoreAnswerCacheEntry(
            identity_digest=identity.digest,
            corpus_fingerprint=identity.corpus_fingerprint,
            generation_fingerprint=identity.generation_fingerprint,
            prompt_fingerprint=identity.prompt_fingerprint,
            grounding_contract_version=identity.grounding_contract_version,
            authorization_fingerprint=identity.authorization_fingerprint,
            answer=context.chisa_reply,
            citations=citations,
            created_at=now,
            expires_at=now + self.policy.ttl_seconds,
        )

    @staticmethod
    def result_is_cacheable(context: ChatContext) -> bool:
        if context.is_cached_answer:
            return False
        if not context.chisa_reply or context.prompt is None:
            return False
        if context.prompt.output_contract_name != "submit_grounded_answer":
            return False
        grounding = (context.tool_res or {}).get("grounding")
        generation = (context.tool_res or {}).get("generation_contract")
        if not isinstance(grounding, dict) or grounding.get("status") != "verified":
            return False
        if not isinstance(generation, dict) or generation.get("abstained") is not False:
            return False
        if not context.citation_ids or len(set(context.citation_ids)) != len(context.citation_ids):
            return False
        evidence = context.prompt.retrieved_evidence
        evidence_ids = {item.evidence_id for item in evidence}
        return bool(
            evidence
            and all(item.kind == "lore" for item in evidence)
            and set(context.citation_ids).issubset(evidence_ids)
        )

    def validate_entry(
        self,
        entry: LoreAnswerCacheEntry,
        identity: LoreAnswerCacheIdentity,
        context: ChatContext,
        *,
        now: float,
    ) -> Literal["hit", "expired", "identity_mismatch", "acl_mismatch"]:
        expected = (
            entry.identity_digest == identity.digest
            and entry.corpus_fingerprint == identity.corpus_fingerprint
            and entry.generation_fingerprint == identity.generation_fingerprint
            and entry.prompt_fingerprint == identity.prompt_fingerprint
            and entry.grounding_contract_version == identity.grounding_contract_version
            and entry.authorization_fingerprint == identity.authorization_fingerprint
        )
        if not expected:
            return "identity_mismatch"
        if entry.expires_at <= now or entry.created_at > now:
            return "expired"
        if not all(self._citation_is_authorized(item, context) for item in entry.citations):
            return "acl_mismatch"
        return "hit"

    @staticmethod
    def _prompt_context(context: ChatContext) -> dict[str, object]:
        return {
            "user_message": context.user_message,
            "intents": sorted(str(intent.value) for intent in context.intents),
            "history": context.history,
            "conversation_summary": context.conversation_summary,
            "current_emotions": context.current_emotions,
            "persona_trait_type": context.persona_trait_type,
            "interaction_count": context.stats.interaction_count if context.stats else None,
            "is_community": context.is_community,
            "speaker_name": context.speaker_name,
            "guild_name": context.guild_name,
            "channel_name": context.channel_name,
            "channel_transcript": context.channel_transcript,
            "topic_summary": context.topic_summary,
            "ambient_context": context.ambient_context,
            "memory_policy": {
                "enabled": context.memory_privacy_policy.long_term_memory_enabled,
                "retention_days": context.memory_privacy_policy.retention_days,
            },
        }

    @staticmethod
    def _authorization_fingerprint(context: ChatContext) -> str:
        return _fingerprint(
            {
                "subject": context.user_id,
                "tenant": context.guild_id,
                "channel": context.channel_id,
                "community": context.is_community,
            }
        )

    @staticmethod
    def _access_binding(access: EvidenceAccess) -> str:
        return _fingerprint(
            {
                "scope": access.scope,
                "subject": access.subject_id,
                "tenant": access.tenant_id,
                "channel": access.channel_id,
            }
        )

    @classmethod
    def _citation(cls, *, item: Evidence) -> CachedCitation:
        return CachedCitation(
            evidence_id=item.evidence_id,
            access_scope=item.access.scope,
            access_binding_fingerprint=cls._access_binding(item.access),
        )

    @classmethod
    def _citation_is_authorized(cls, citation: CachedCitation, context: ChatContext) -> bool:
        allowed: list[EvidenceAccess]
        if citation.access_scope == "public":
            allowed = [EvidenceAccess(scope="public")]
        elif citation.access_scope == "user":
            allowed = [EvidenceAccess(scope="user", subject_id=context.user_id)]
        elif context.guild_id:
            allowed = [EvidenceAccess(scope="tenant", tenant_id=context.guild_id)]
            if context.channel_id:
                allowed.append(
                    EvidenceAccess(
                        scope="tenant",
                        tenant_id=context.guild_id,
                        channel_id=context.channel_id,
                    )
                )
        else:
            return False
        return citation.access_binding_fingerprint in {
            cls._access_binding(access) for access in allowed
        }
