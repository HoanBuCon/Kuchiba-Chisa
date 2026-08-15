from dataclasses import dataclass

@dataclass(frozen=True)
class RAGTuning:
    """Tuning parameters for the RAG retrieval and routing pipelines."""
    TOP_K: int = 5
    SCORE_THRESHOLD: float = 0.35

    # Multi-signal hybrid weights (Sum = 1.0) — Optimized for Cross-Lingual Wiki Retrieval (VN query -> EN corpus)
    WEIGHT_VECTOR: float = 0.80      # Dense vector cross-lingual semantic similarity (multilingual-e5-small)
    WEIGHT_KEYWORD: float = 0.10     # Sparse text keyword/BM25 token overlap (for exact entity names)
    WEIGHT_METADATA: float = 0.10    # Metadata match (canonical_name, heading_path, entities graph)

