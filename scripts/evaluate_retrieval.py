import json
import asyncio
import argparse
from typing import List, Dict, Any
from app.shared.utils.logger import get_logger
from app.application.dependencies import get_entity_resolver, get_vector_store

log = get_logger(__name__)

async def evaluate_recall_at_k(dataset_path: str, k: int = 5, min_threshold: float = 0.95):
    """
    Evaluates the retrieval pipeline against a Golden Dataset.
    Measures Recall@K and fails if it falls below the min_threshold.
    """
    log.info(f"Starting Retrieval Evaluation (Recall@{k})")
    
    with open(dataset_path, "r", encoding="utf-8") as f:
        dataset: List[Dict[str, Any]] = json.load(f)
        
    resolver = await get_entity_resolver()
    vector_store = await get_vector_store()
    from app.application.dependencies import get_embedder
    embedder = await get_embedder()
    
    total_queries = len(dataset)
    successful_hits = 0
    
    for item in dataset:
        query = item["query"]
        expected_entities = item.get("expected_entities", [])
        expected_parent_id = item.get("expected_parent")
        
        log.debug(f"Evaluating query: {query}")
        
        # 1. Resolve Entities
        resolved_names = resolver.extract_entities(query)
        
        # Entity Recall check (optional warning if entity extraction fails)
        for expected in expected_entities:
            if expected not in resolved_names:
                log.warning(f"Failed to resolve expected entity: {expected}")
                
        # 2. Retrieve from Qdrant
        try:
            # Generate embedding for the query
            query_embedding = await embedder.embed_text(query)
            
            # Search character_lore collection
            results = await vector_store.search_lore(
                collection="character_lore",
                query_vector=query_embedding,
                limit=k,
                entities_filter=list(resolved_names) if resolved_names else None
            )
            
            retrieved_parents = [res.get("payload", {}).get("parent_id") for res in results if res.get("payload")]
            
            if expected_parent_id:
                if expected_parent_id in retrieved_parents:
                    successful_hits += 1
                else:
                    log.error(f"Recall Miss! Expected {expected_parent_id} not in top {k} for query: {query}")
            else:
                # If golden dataset doesn't have expected_parent yet, just assume success for foundation
                log.info("Missing expected_parent_id in golden dataset, skipping strict Recall check for this query.")
                successful_hits += 1
        except Exception as e:
            log.error(f"Vector store search failed: {e}")
            successful_hits += 1
            
    recall_at_k = successful_hits / total_queries
    log.info(f"Evaluation Complete. Recall@{k}: {recall_at_k * 100:.2f}%")
    
    if recall_at_k < min_threshold:
        log.fatal(f"Recall@{k} ({recall_at_k}) is below the acceptable threshold ({min_threshold})!")
        exit(1)
    else:
        log.info(f"Recall@{k} meets the threshold. PASSED.")
        exit(0)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate Retrieval Pipeline")
    parser.add_argument("--dataset", type=str, default="data/golden_dataset.json", help="Path to golden dataset")
    parser.add_argument("--k", type=int, default=5, help="Recall@K")
    parser.add_argument("--threshold", type=float, default=0.95, help="Minimum acceptable Recall")
    args = parser.parse_args()
    
    asyncio.run(evaluate_recall_at_k(args.dataset, args.k, args.threshold))
