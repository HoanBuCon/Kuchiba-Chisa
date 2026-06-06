import asyncio
import os
import re
import datetime
from typing import Any
from app.infrastructure.llm.adapters.base import StructuredPrompt, LLMResponse

LOG_FILE_PATH = "llm_api_clean.txt"

def _get_next_index() -> int:
    if not os.path.exists(LOG_FILE_PATH):
        return 1
    try:
        with open(LOG_FILE_PATH, "r", encoding="utf-8") as f:
            content = f.read()
        matches = re.findall(r"=====\s*LƯỢT\s+(\d+)\s*=====", content)
        if matches:
            return max(int(m) for m in matches) + 1
    except Exception:
        pass
    return 1

def _write_log_sync(prompt: StructuredPrompt, response: LLMResponse) -> None:
    idx = _get_next_index()
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Format chat history
    history_lines = []
    if prompt.history:
        for msg in prompt.history:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            history_lines.append(f"- {role}: {content}")
    else:
        history_lines.append("(Không có lịch sử trò chuyện)")
    history_str = "\n".join(history_lines)
    
    # Format parsed response
    parsed_lines = []
    if response.parsed:
        for k, v in response.parsed.items():
            parsed_lines.append(f"{k}: {v}")
    else:
        parsed_lines.append("(Không thể phân tích dữ liệu)")
    parsed_str = "\n".join(parsed_lines)
    
    # Format RAG information
    decisions = prompt.rag_decisions or {}
    use_lore = decisions.get("use_lore", False)
    use_memory = decisions.get("use_memory", False)
    decisions_str = f"Lấy Lore (use_lore): {use_lore} | Lấy Ký ức (use_memory): {use_memory}"
    
    lore_lines = []
    if prompt.retrieved_lore:
        for i, chunk in enumerate(prompt.retrieved_lore, 1):
            chunk_snippet = chunk.replace("\n", " ").strip()
            lore_lines.append(f"  + Mảnh {i}: {chunk_snippet}")
    else:
        lore_lines.append("  (Không có dữ liệu Lore được lấy)")
    lore_str = "\n".join(lore_lines)
    
    memory_lines = []
    if prompt.retrieved_memories:
        for i, mem in enumerate(prompt.retrieved_memories, 1):
            text = getattr(mem, "text_content", str(mem))
            tier = getattr(mem, "memory_tier", "N/A")
            score = getattr(mem, "final_score", 0.0)
            comps = getattr(mem, "components", {})
            memory_lines.append(f"  + Ký ức {i}: {text} (Loại: {tier}, Score: {score:.4f}, Components: {comps})")
    else:
        memory_lines.append("  (Không có dữ liệu Ký ức được lấy)")
    memories_str = "\n".join(memory_lines)
    
    log_content = f"""===== LƯỢT {idx} =====
Thời gian: {now_str}
Model sử dụng: {response.model}

--------------------------------------------------------------------------------
[1. REQUEST GỬI LÊN API LLM]
--------------------------------------------------------------------------------
[RAG RETRIEVAL INFO]
- Quyết định RAG Router: {decisions_str}
- Kết quả truy xuất Lore:
{lore_str}
- Kết quả truy xuất Memory:
{memories_str}

[SYSTEM PROMPT]
{prompt.system}

[CHAT HISTORY]
{history_str}

[USER MESSAGE]
{prompt.user_message}

--------------------------------------------------------------------------------
[2. RESPONSE TRẢ VỀ TỪ API LLM]
--------------------------------------------------------------------------------
[FINISH REASON]
{response.finish_reason}

[USAGE METADATA]
Input Tokens: {response.input_tokens}
Output Tokens: {response.output_tokens}
Total Tokens: {response.input_tokens + response.output_tokens}

[RAW CONTENT]
{response.raw_content}

[PARSED JSON]
{parsed_str}

================================================================================

"""
    # Open with 'a' mode for appending, encoding utf-8 to support Vietnamese
    with open(LOG_FILE_PATH, "a", encoding="utf-8") as f:
        f.write(log_content)

async def log_llm_transaction(prompt: StructuredPrompt, response: LLMResponse) -> None:
    """
    Asynchronously logs a complete LLM transaction (Request & Response) to a clean txt file.
    Runs inside a thread pool to avoid blocking the event loop.
    """
    try:
        await asyncio.to_thread(_write_log_sync, prompt, response)
    except Exception as e:
        # Prevent logging errors from crashing the main chat flow
        import logging
        logging.getLogger(__name__).warning(f"Failed to write clean LLM log: {e}")
