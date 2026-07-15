import os
import sys
import json
import time
import asyncio

sys.path.append(os.getcwd())

from app.infrastructure.database.engine import AsyncSessionFactory
from app.infrastructure.vector.qdrant.qdrant_service import qdrant_service
from app.infrastructure.embeddings.fastembed_adapter import FastEmbedAdapter
from app.domain.services.rag.entity_resolver import EntityResolver
from app.domain.services.rag.retriever_lore import LoreRetriever
from app.domain.tuning.rag import RAGTuning
from app.shared.utils.logger import get_logger

log = get_logger(__name__)

GOLDEN_DATASET_PATH = "data/golden_dataset.json"

async def run_benchmark():
    if not os.path.exists(GOLDEN_DATASET_PATH):
        print(f"Error: Golden dataset not found at {GOLDEN_DATASET_PATH}")
        return

    with open(GOLDEN_DATASET_PATH, "r", encoding="utf-8") as f:
        dataset = json.load(f)

    print(f"Loaded {len(dataset)} questions from Golden Dataset.")
    print("Initializing components...")

    embedder = FastEmbedAdapter()
    entity_resolver = EntityResolver()
    entity_resolver.load()
    lore_retriever = LoreRetriever(qdrant_service)

    total_latency = 0.0
    queries_processed = 0

    async with AsyncSessionFactory() as session:
        for idx, item in enumerate(dataset):
            query = item["query"]
            print(f"\n--- Query {idx + 1}: {query}")

            start_time = time.perf_counter()

            # 1. Entity Resolution
            extracted = set(entity_resolver.extract_entities(query))
            expanded = entity_resolver.expand_entities(extracted)
            
            # 2. Embedding
            query_vector = await embedder.embed_text(query)
            
            # 3. Retrieval
            retrieved_results = await lore_retriever.retrieve_lore_parent_child(
                collection="lore",
                query_vector=query_vector,
                session=session,
                query_text=query,
                top_k=5,
                score_threshold=RAGTuning.SCORE_THRESHOLD,
                entities_filter=list(expanded) if expanded else None
            )

            latency = time.perf_counter() - start_time
            total_latency += latency
            queries_processed += 1

            print(f"  Latency: {latency:.4f}s")
            print(f"  Extracted Entities: {extracted}")
            print(f"  Expanded Entities: {expanded}")
            print(f"  Retrieved Parent Chunks: {len(retrieved_results)}")
            
            if len(retrieved_results) > 0:
                print(f"  Top Match Score: {retrieved_results[0][1]:.4f}")
            else:
                print("  [!] No chunks retrieved.")

    if queries_processed > 0:
        avg_latency = total_latency / queries_processed
        print("\n" + "="*40)
        print(" BENCHMARK COMPLETE")
        print("="*40)
        print(f"Total Queries: {queries_processed}")
        print(f"Average Latency: {avg_latency:.4f}s per query")
        print("="*40)

if __name__ == "__main__":
    asyncio.run(run_benchmark())
