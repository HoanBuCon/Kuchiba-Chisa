from typing import Any, List, Dict
from pydantic import BaseModel

class ScoredMemory(BaseModel):
    id: str
    text_content: str
    memory_type: str
    memory_tier: str
    final_score: float
    metadata: Dict[str, Any] = {}
    components: Dict[str, float]

class RAGContext(BaseModel):
    lore_chunks: List[str]
    memories: List[str]
    guild_memories: List[str] = []
    tool_output_msg: str = ""
    is_aligned: bool = True
    alignment_reason: str = ""
    thinking_steps: List[Dict[str, Any]] = []
