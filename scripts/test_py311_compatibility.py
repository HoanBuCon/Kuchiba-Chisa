"""
Python 3.11 Async Compatibility and Performance Smoke Test
Checks event loop, db connection, redis pings, and basic background tasks.
"""
import asyncio
import time
from typing import Any

from app.config.settings import settings
from app.infrastructure.logging.logger import configure_logging, get_logger
from app.infrastructure.database.engine import check_database_health
from app.infrastructure.cache.redis.redis_service import redis_service
from app.infrastructure.vector.qdrant.qdrant_service import qdrant_service
from app.infrastructure.queue.tasks.memory_tasks import summarize_conversation

configure_logging()
log = get_logger(__name__)

async def test_async_compatibility() -> dict[str, Any]:
    log.info("Starting Async Compatibility Suite (Python 3.11)")
    results = {}
    
    # 1. DB Connection Test
    try:
        db_ok = await check_database_health()
        results["db_connect"] = "PASS" if db_ok else "FAIL"
    except Exception as e:
        results["db_connect"] = f"ERROR: {e}"

    # 2. Redis Concurrency Test
    try:
        start_time = time.monotonic()
        # Fire 100 concurrent pings
        ping_tasks = [redis_service.health_check() for _ in range(100)]
        ping_results = await asyncio.gather(*ping_tasks)
        elapsed = time.monotonic() - start_time
        results["redis_100_pings"] = "PASS" if all(ping_results) else "FAIL"
        results["redis_throughput"] = f"{elapsed:.3f}s for 100 pings"
    except Exception as e:
        results["redis_100_pings"] = f"ERROR: {e}"

    # 3. Vector DB Concurrency (Mock via health checks)
    try:
        start_time = time.monotonic()
        # Fire 20 concurrent pings
        q_tasks = [qdrant_service.health_check() for _ in range(20)]
        q_results = await asyncio.gather(*q_tasks)
        elapsed = time.monotonic() - start_time
        results["qdrant_20_pings"] = "PASS" if all(q_results) else "FAIL"
        results["qdrant_throughput"] = f"{elapsed:.3f}s for 20 pings"
    except Exception as e:
        results["qdrant_20_pings"] = f"ERROR: {e}"
        
    # 4. Celery Async Trigger (Broker check)
    try:
        # Just queue a stub task to ensure broker connection works without hanging
        task = summarize_conversation.delay("test_conv", "test_user")
        results["celery_submit"] = f"PASS (Task ID: {task.id})"
    except Exception as e:
        results["celery_submit"] = f"ERROR: {e}"

    return results

if __name__ == "__main__":
    import sys
    # Verify Python version strictly
    if sys.version_info < (3, 11):
        print("ERROR: Not running in Python 3.11+")
        sys.exit(1)
        
    print(f"Running on Python {sys.version}")
    
    # Run async test suite
    results = asyncio.run(test_async_compatibility())
    
    print("\n--- TEST RESULTS ---")
    for key, val in results.items():
        print(f"{key:20s}: {val}")
    
    # Exit with code 1 if any failure
    if any(str(v).startswith("FAIL") or str(v).startswith("ERROR") for v in results.values()):
        sys.exit(1)
    
    print("\n✅ All async compatibility checks passed.")
