import asyncio
import os
import sys

# Add project root to sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(PROJECT_ROOT)

from app.domain.services.production_pipeline.tools.web_search import WebSearchAgentTool
from app.domain.services.production_pipeline.production_context_builder import ProductionContextBuilder
from app.infrastructure.llm.adapters.deepseek import DeepSeekAdapter
from scratch.test_summarize import FastEmbedAdapter
from app.infrastructure.database.models.emotion_state import EmotionState

async def main():
    print("=" * 70)
    print("      TESTING WEB SEARCH OPTIMIZATION & CONTEXT-AWARE ROUTING")
    print("=" * 70)

    # Initialize components
    embedder = FastEmbedAdapter()
    llm = DeepSeekAdapter()
    web_search_tool = WebSearchAgentTool()
    context_builder = ProductionContextBuilder()

    # 1. Giả định lịch sử trò chuyện có context Wuthering Waves
    history = [
        {"role": "user", "content": "Em có thích game Wuthering Waves không Chisa?"},
        {"role": "assistant", "content": "Có chứ Senpai, thế giới Huanglong với những Resonator và Tacet Discord luôn là đề tài nghiên cứu cấu trúc thú vị đối với em. Sao vậy Senpai?"},
    ]

    # 2. Câu hỏi mơ hồ tiếp theo của User (không nhắc lại tên game)
    user_message = "Thế bản cập nhật 1.3 có gì mới vậy em?"
    print(f"Lịch sử chat giả lập:\n- USER: {history[0]['content']}\n- ASSISTANT: {history[1]['content']}")
    print(f"\nCâu hỏi mơ hồ mới nhất: '{user_message}'")

    print("\n[*] Đang chạy trích xuất query tối ưu ngữ cảnh...")
    search_query = await web_search_tool._extract_search_query(
        user_message=user_message,
        llm=llm,
        history=history
    )
    print(f"[+] Query tìm kiếm tối ưu thu được: '{search_query}'")
    
    # Kỳ vọng query tìm kiếm phải được bổ sung context (ví dụ có "Wuthering Waves 1.3")
    if "wuthering" in search_query.lower() or "waves" in search_query.lower() or "chisa" in search_query.lower():
        print("  [✓] Pass: Query trích xuất có chứa context chính xác!")
    else:
        print("  [❌] Fail: Query không chứa context!")

    print("\n[*] Tiến hành chạy DuckDuckGo Search thực tế...")
    search_result = await web_search_tool._web_search(search_query)
    
    print(f"[+] Status tìm kiếm: {search_result.get('status')}")
    tool_output = search_result.get("message", "")
    print(f"[+] Snippets thô thu được:\n{tool_output}")

    # 3. Lắp prompt thông qua ProductionContextBuilder để kiểm tra phản hồi của Chisa
    print("\n[*] Tiến hành lắp prompt thông qua ProductionContextBuilder...")
    dummy_emotion = EmotionState(joy=0.5, sadness=0.0, trust=0.8, irritation=0.0, attachment=0.6)
    
    prompt = context_builder.build(
        emotion=dummy_emotion,
        attachment_bonus=0.05,
        memories=[],
        lore=[],
        history=history,
        user_message=user_message,
        intent_name="SYSTEM_ACTION",
        tool_result=tool_output
    )

    print("\n[*] Gửi prompt đến LLM chính để sinh câu thoại của Chisa...")
    response = await llm.generate(prompt)
    parsed = response.parsed or {}
    chisa_response = parsed.get("response", "")
    print(f"\n[+] Phản hồi của Chisa:\n{chisa_response}")

    # Kiểm tra xem có chứa câu dẫn máy móc không
    forbidden_phrases = [
        "theo kết quả", "em vừa tra", "dưới đây là kết quả", 
        "kết quả tìm kiếm", "theo thông tin trên mạng", "internet"
    ]
    has_forbidden = any(p in chisa_response.lower() for p in forbidden_phrases)
    if not has_forbidden:
        print("\n  [✓] Pass: Chisa trả lời tự nhiên, không dùng câu dẫn máy móc!")
    else:
        print("\n  [❌] Warning: Lời thoại của Chisa vẫn chứa câu dẫn máy móc. Hãy tinh chỉnh prompt.")

if __name__ == "__main__":
    asyncio.run(main())
