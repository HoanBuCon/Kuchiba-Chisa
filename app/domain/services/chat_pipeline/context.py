import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.domain.entities.emotion import EmotionState
from app.domain.entities.user import UserStats
from app.domain.interfaces.llm_provider import StructuredPrompt
from app.domain.interfaces.session import IDbSession
from app.domain.models.intent_result import ChatIntent, IntentResult
from app.domain.services.context_budget_manager import BudgetAudit
from app.domain.services.rag import RAGContext


@dataclass
class ChatContext:
    # Initial state
    session: IDbSession
    user_id: str
    user_message: str
    on_token: Callable[[str], Any] | None = None
    trace_id: str | None = None

    # Community Mode Extensions
    is_community: bool = False
    channel_id: str | None = None
    guild_id: str | None = None
    channel_name: str = "general"
    guild_name: str | None = None
    speaker_name: str | None = None
    recent_community_messages: list[Any] = field(default_factory=list)
    channel_transcript: str = ""
    topic_summary: str | None = None
    recent_social_trace: dict[str, Any] | None = None
    ambient_context: str | None = None
    
    # State populated during pipeline execution
    user_uuid: uuid.UUID | None = None
    conv_id: uuid.UUID | None = None
    stats: UserStats | None = None
    emotion: EmotionState | None = None
    history: list[dict[str, str]] = field(default_factory=list)
    conversation_summary: str | None = None
    attachment_bonus_raw: float = 0.0
    current_emotions: dict[str, float] = field(default_factory=dict)
    
    # Intent and Routing
    cleaned_query: str = ""
    rewritten_query: str = ""
    rewrite_method: str = "FAST_PATH"  # "BYPASS", "FAST_PATH", "LLM_FLASH", "FAST_PATH_FALLBACK"
    needs_vector_search: bool = True
    needs_web_search: bool = False
    query_vector: list[float] | None = None
    intent_result: IntentResult | None = None
    persona_trait_type: str | None = None  # "PERSONALITY", "PROFILE", "BOTH", None
    _is_small_talk: bool = False
    _intents: list[Any] = field(default_factory=list)

    @property
    def is_small_talk(self) -> bool:
        if self.intent_result is not None:
            knowledge_intents = {ChatIntent.LORE, ChatIntent.MEMORY, ChatIntent.SYSTEM_ACTION}
            if any(ki in self.intent_result.intents for ki in knowledge_intents):
                return False
            return self.intent_result.intents == [ChatIntent.SMALL_TALK]
        return self._is_small_talk

    @is_small_talk.setter
    def is_small_talk(self, value: bool) -> None:
        self._is_small_talk = value

    @property
    def intents(self) -> list[Any]:
        if self.intent_result is not None:
            return self.intent_result.intents
        return self._intents

    @intents.setter
    def intents(self, value: list[Any]) -> None:
        self._intents = value
    
    # Tool Routing
    tool_output_msg: str | None = None
    tool_name: str = "none"
    tool_score: float = 0.0
    tool_res: dict[str, Any] | None = None
    
    # RAG
    rag_context: RAGContext | None = None
    
    # Context Building
    final_user_message: str = ""
    prompt: StructuredPrompt | None = None
    budget_audit: BudgetAudit | None = None
    
    # LLM Generation
    chisa_reply: str = ""
    is_cached_answer: bool = False
    estimated_input_tokens: int = 0
    estimated_output_tokens: int = 0
    
    # Multimodal Vision & Reverse Image Retrieval Extensions
    images: list[str] = field(default_factory=list)
    processed_images: list[dict[str, Any]] = field(default_factory=list)
    has_images: bool = False
    is_ephemeral_reference: bool = False
    image_analysis_summary: str | None = None
    vision_failed: bool = False
    needs_image_retrieval: bool = False
    retrieved_images: list[dict[str, Any]] = field(default_factory=list)
    attached_images: list[str] = field(default_factory=list)
    image_tags: list[str] = field(default_factory=list)
    visual_caption: str | None = None

    # Final Result
    updated_emotions: dict[str, float] = field(default_factory=dict)
    images_processed: list[dict[str, Any]] = field(default_factory=list)
