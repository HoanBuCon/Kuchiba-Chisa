from dataclasses import dataclass

@dataclass(frozen=True)
class RAGTuning:
    """Tuning parameters for the RAG retrieval and routing pipelines."""
    TOP_K: int = 5
    SCORE_THRESHOLD: float = 0.35

    # Multi-signal hybrid weights (Sum = 1.0)
    WEIGHT_VECTOR: float = 0.60      # Dense vector semantic similarity
    WEIGHT_KEYWORD: float = 0.25     # Sparse text keyword/BM25 token overlap
    WEIGHT_METADATA: float = 0.15    # Metadata match (canonical_name, heading_path, entities graph)

