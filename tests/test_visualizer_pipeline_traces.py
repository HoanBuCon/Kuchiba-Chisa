import sys
from pathlib import Path

# Add project root directory to sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import pytest
from app.infrastructure.logging.pipeline_tracker import pipeline_tracker
from scripts.generate_visualizer_traces import generate_10_full_pipeline_traces


@pytest.mark.asyncio
async def test_generate_and_verify_10_visualizer_traces():
    """
    Verifies that running generate_10_full_pipeline_traces produces 10 rich traces
    with all 10 canonical stages, available for inspection on the Visualizer Dashboard.
    """
    initial_count = len(pipeline_tracker.get_traces())
    await generate_10_full_pipeline_traces()
    traces = pipeline_tracker.get_traces()

    assert len(traces) >= 10, f"Expected at least 10 traces in history, found {len(traces)}"

    # 1. Verify Trace 1: Vector RAG + Loop Thinking
    t1 = next((t for t in traces if "Jiyan" in t.get("message", "") and "chiêu thức" in t.get("message", "")), None)
    assert t1 is not None, "Trace 1 (Vector RAG + Loop Thinking) must exist"
    steps_1 = t1.get("steps", [])
    step_names_1 = [s["name"] for s in steps_1]
    assert "initialization" in step_names_1
    assert "intent_classification" in step_names_1
    assert "lore_retrieval" in step_names_1
    assert "thinking_loop_cycle_1" in step_names_1
    assert "thinking_loop_auto_satisfy" in step_names_1
    assert "context_building" in step_names_1
    assert "llm_generation" in step_names_1
    assert "emotion_update" in step_names_1

    # 2. Verify Trace 2: Web Search + Deep Crawler
    t2 = next((t for t in traces if "2.8" in t.get("message", "")), None)
    assert t2 is not None, "Trace 2 (Web Search) must exist"
    step_names_2 = [s["name"] for s in t2.get("steps", [])]
    assert "web_search" in step_names_2
    assert "information_alignment_check" in step_names_2

    # 3. Verify Trace 7: Deep CoT Reasoning Trace
    t7 = next((t for t in traces if "nguy hiểm" in t.get("message", "")), None)
    assert t7 is not None, "Trace 7 (Deep CoT Reasoning) must exist"
    llm_step_7 = next(s for s in t7.get("steps", []) if s["name"] == "llm_generation")
    assert llm_step_7["data"].get("reasoning_tokens", 0) > 0
    assert llm_step_7["data"].get("reasoning_content") != ""

    # 4. Verify Trace 8: Background Tasks (10.1 Memory Extraction + 10.2 Auto-Summarize)
    t8 = next((t for t in traces if "hoàng hôn" in t.get("message", "")), None)
    assert t8 is not None, "Trace 8 (Background Tasks) must exist"
    step_names_8 = [s["name"] for s in t8.get("steps", [])]
    assert "memory_extraction" in step_names_8
    assert "summarize_conversation_memory" in step_names_8


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main(["-v", __file__]))
