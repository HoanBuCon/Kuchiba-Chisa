import uuid
from typing import Optional, List, Dict, Any, Callable
from dataclasses import dataclass, field
from app.domain.interfaces.session import IDbSession

from app.domain.interfaces.uow import IUnitOfWork
from app.domain.entities.emotion import EmotionState
from app.domain.services.rag import RAGContext
from app.domain.services.context_budget_manager import BudgetAudit
from app.domain.interfaces.llm_provider import StructuredPrompt

@dataclass
class ChatContext:
    # Initial state
    session: IDbSession
    user_id: str
    user_message: str
    on_token: Optional[Callable[[str], Any]] = None
    
    # State populated during pipeline execution
    user_uuid: Optional[uuid.UUID] = None
    conv_id: Optional[uuid.UUID] = None
    stats: Optional[Any] = None
    emotion: Optional[EmotionState] = None
    history: List[Dict[str, str]] = field(default_factory=list)
    attachment_bonus_raw: float = 0.0
    current_emotions: Dict[str, float] = field(default_factory=dict)
    
    # Intent and Routing
    is_small_talk: bool = False
    cleaned_query: str = ""
    query_vector: Optional[List[float]] = None
    intents: List[Any] = field(default_factory=list)
    
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
    estimated_input_tokens: int = 0
    estimated_output_tokens: int = 0
    
    # Final Result
    updated_emotions: Dict[str, float] = field(default_factory=dict)
