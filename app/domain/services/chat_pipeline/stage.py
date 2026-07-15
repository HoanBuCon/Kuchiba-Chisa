from abc import ABC, abstractmethod
from app.domain.services.chat_pipeline.context import ChatContext

class PipelineStage(ABC):
    """Abstract base class for all chat pipeline stages."""
    
    @abstractmethod
    async def process(self, context: ChatContext) -> ChatContext:
        """Process the given context and return the updated context."""
        pass
