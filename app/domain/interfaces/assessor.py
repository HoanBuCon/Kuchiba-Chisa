from abc import ABC, abstractmethod
from typing import Tuple, Optional, List
from app.domain.interfaces.llm_provider import BaseLLMAdapter

class IContextAssessor(ABC):
    @abstractmethod
    async def assess_alignment(
        self,
        user_message: str,
        context_text: str,
        llm: BaseLLMAdapter,
        history: Optional[List[dict]] = None,
        conversation_summary: Optional[str] = None,
    ) -> Tuple[bool, str, str, bool]:
        pass
