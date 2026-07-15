from abc import ABC, abstractmethod
from typing import TypeVar, Generic, Any
import uuid
from pydantic import BaseModel

TInput = TypeVar('TInput')
TOutput = TypeVar('TOutput')

class PipelineMetrics(BaseModel):
    duration_seconds: float
    items_processed: int
    items_failed: int
    items_skipped: int

class PipelineResult(BaseModel, Generic[TOutput]):
    output: TOutput
    metrics: PipelineMetrics

class IPipelineStage(ABC, Generic[TInput, TOutput]):
    """
    Abstract definition of an independent ingestion pipeline stage.
    """
    
    @abstractmethod
    async def execute(self, job_id: uuid.UUID, input_data: TInput) -> PipelineResult[TOutput]:
        """
        Receives immutable input and returns immutable output. Logs to pipeline_events using job_id.
        """
        pass
