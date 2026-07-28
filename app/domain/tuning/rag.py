from dataclasses import dataclass

@dataclass(frozen=True)
class RAGTuning:
    """Tuning parameters for the RAG retrieval and routing pipelines."""
    TOP_K: int = 5
    SCORE_THRESHOLD: float = 0.35
