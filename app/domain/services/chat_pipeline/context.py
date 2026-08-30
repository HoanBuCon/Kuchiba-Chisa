import uuid
from typing import Optional, List, Dict, Any, Callable
from dataclasses import dataclass, field
from app.domain.interfaces.session import IDbSession

from app.domain.entities.emotion import EmotionState
from app.domain.services.rag import RAGContext
from app.domain.services.context_budget_manager import BudgetAudit
from app.domain.interfaces.llm_provider import StructuredPrompt

from app.domain.models.intent_result import IntentResult, ChatIntent

@dataclass
class ChatContext:
    # Initial state
    session: IDbSession
    user_id: str
    user_message: str
    on_token: Optional[Callable[[str], Any]] = None
    trace_id: Optional[str] = None

    # Community Mode Extensions
    is_community: bool = False
    channel_id: Optional[str] = None
    guild_id: Optional[str] = None
    channel_name: str = "general"
    guild_name: Optional[str] = None
    speaker_name: Optional[str] = None
    recent_community_messages: List[Any] = field(default_factory=list)
    channel_transcript: str = ""
    topic_summary: Optional[str] = None
    recent_social_trace: Optional[Dict[str, Any]] = None
    ambient_context: Optional[str] = None
    
    # State populated during pipeline execution
    user_uuid: Optional[uuid.UUID] = None
    conv_id: Optional[uuid.UUID] = None
    stats: Optional[Any] = None
    emotion: Optional[EmotionState] = None
    history: List[Dict[str, str]] = field(default_factory=list)
    conversation_summary: Optional[str] = None
    attachment_bonus_raw: float = 0.0
    current_emotions: Dict[str, float] = field(default_factory=dict)
    
    # Intent and Routing
    cleaned_query: str = ""
    rewritten_query: str = ""
    rewrite_method: str = "FAST_PATH"  # "BYPASS", "FAST_PATH", "LLM_FLASH", "FAST_PATH_FALLBACK"
    needs_vector_search: bool = True
    needs_web_search: bool = False
    query_vector: Optional[List[float]] = None
    intent_result: Optional[IntentResult] = None
    persona_trait_type: Optional[str] = None  # "PERSONALITY", "PROFILE", "BOTH", None
    _is_small_talk: bool = False
    _intents: List[Any] = field(default_factory=list)

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
    def intents(self) -> List[Any]:
        if self.intent_result is not None:
            return self.intent_result.intents
        return self._intents

    @intents.setter
    def intents(self, value: List[Any]) -> None:
        self._intents = value
    
    # Tool Routing
    tool_output_msg: Optional[str] = None
    tool_name: str = "none"
    tool_score: float = 0.0
    tool_res: Optional[Dict[str, Any]] = None
    
    # RAG
    rag_context: Optional[RAGContext] = None
    
    # Context Building
    final_user_message: str = ""
    prompt: Optional[StructuredPrompt] = None
    budget_audit: Optional[BudgetAudit] = None
    
    # LLM Generation
    chisa_reply: str = ""
    is_cached_answer: bool = False
    estimated_input_tokens: int = 0
    estimated_output_tokens: int = 0
    
    # Multimodal Vision & Reverse Image Retrieval Extensions
    images: List[str] = field(default_factory=list)
    processed_images: List[Dict[str, Any]] = field(default_factory=list)
    has_images: bool = False
    is_ephemeral_reference: bool = False
    image_analysis_summary: Optional[str] = None
    vision_failed: bool = False
    needs_image_retrieval: bool = False
    retrieved_images: List[Dict[str, Any]] = field(default_factory=list)
    attached_images: List[str] = field(default_factory=list)

    # Final Result
    updated_emotions: Dict[str, float] = field(default_factory=dict)
    images_processed: List[Dict[str, Any]] = field(default_factory=list)
