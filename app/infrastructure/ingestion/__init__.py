"""
Ingestion Pipeline — Production Architecture v1.1

Transforms raw Wiki data (10K–50K pages) into high-quality vector-ready chunks
through a Canonical Dataset intermediate layer.

Pipeline flow:
    Wiki → Crawl → Parse → Canonical Dataset (★) → Chunk → Validate → Embed → Index

The Canonical Dataset (canonical.jsonl) is the immutable decoupling boundary
between expensive upstream processing and cheap downstream experimentation.
"""
