import asyncio
import httpx
import sys
import os
import uuid
from typing import Optional

# Ensure UTF-8 output encoding for printing to console
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

PROJECT_ROOT = r"d:\Hoc_Tap\Code\Du_An_Ca_Nhan\Chisa_bot\kuchiba_chisa"
sys.path.append(PROJECT_ROOT)

from app.infrastructure.database.engine import AsyncSessionFactory
from app.infrastructure.database.models.user import User
from sqlalchemy import select

async def get_test_user_id() -> str:
    async with AsyncSessionFactory() as session:
        stmt = select(User).where(User.username == "test_lore_user")
        existing = (await session.execute(stmt)).scalar_one_or_none()
        if existing:
            return str(existing.id)
        
        u = User(id=uuid.uuid4(), username="test_lore_user", discord_id="456")
        session.add(u)
        await session.commit()
        return str(u.id)

async def send_message_with_retry(client: httpx.AsyncClient, chat_url: str, payload: dict) -> tuple[Optional[str], Optional[dict]]:
    max_retries = 4
    backoff_delay = 5.0
    for attempt in range(1, max_retries + 1):
        try:
            response = await client.post(chat_url, json=payload)
            if response.status_code in [429, 500]:
                print(f"  [!] Received status {response.status_code}, retrying in {backoff_delay}s... (Attempt {attempt}/{max_retries})")
                await asyncio.sleep(backoff_delay)
                backoff_delay *= 2.0
                continue
            response.raise_for_status()
            data = response.json()
            return data.get("response"), data.get("emotions")
        except Exception as e:
            print(f"  [!] Attempt {attempt} failed: {e}")
            if attempt < max_retries:
                await asyncio.sleep(backoff_delay)
                backoff_delay *= 2.0
    return None, None

async def main():
    # ── Chọn mode ──────────────────────────────────────────────────────────────
    print("=" * 60)
    print("  CHISA LORE BENCHMARK TOOL")
    print("=" * 60)
    print("  [1] Câu hỏi đầy đủ ngữ cảnh  (Full Context – dễ)")
    print("  [2] Câu hỏi ngắn / ẩn ý      (Implicit Benchmark – khó)")
    print("-" * 60)
    mode_env = os.environ.get("LORE_TEST_MODE")
    if mode_env in ("1", "2"):
        mode = int(mode_env)
        print(f"Selecting mode {mode} from environment variable LORE_TEST_MODE")
    elif not sys.stdin.isatty():
        mode = 2
        print("Non-interactive terminal detected: defaulting to mode 2 (Implicit Benchmark)")
    else:
        while True:
            try:
                choice = input("Chọn mode (1 hoặc 2): ").strip()
                if choice in ("1", "2"):
                    break
                print("  ⚠️  Vui lòng nhập 1 hoặc 2.")
            except (EOFError, KeyboardInterrupt):
                choice = "2"
                break
        mode = int(choice)
    print()
    # ───────────────────────────────────────────────────────────────────────────

    user_id = await get_test_user_id()
    chat_url = "http://localhost:8000/api/v1/chat"
    clear_url = f"http://localhost:8000/api/v1/chat/clear/{user_id}"
    
    # Set 1: Full/Explicit Prompts (Detailed contextual leading hints)
    set1_questions = [
        ("Thông tin cơ bản & Trường học", "Chào em Chisa, em giới thiệu bản thân một chút và kể cho anh nghe về trường em đang học đi nhé!"),
        ("Sức mạnh & Resonance Forte", "Anh tò mò về năng lực Resonance đặc biệt của em. Cây kéo khổng lồ đó hoạt động ra sao và em nhìn thấy những gì?"),
        ("Rủi ro năng lực & Vòng cổ", "Tại sao em lại phải đeo một thiết bị ở cổ vậy? Có phải liên quan đến rủi ro Overclocking không em?"),
        ("Vòng lặp Honami & Nhật ký Sumika", "Kể cho anh nghe về khoảng thời gian em bị kẹt ở Honami đi, và cuốn nhật ký của chị Sumika đã giúp ích gì cho em vậy?"),
        ("Sở thích, Mèo & Trà bánh", "Em có sở thích gì đặc biệt không, ví dụ như nuôi mèo hay làm trà bánh gì đó? Anh cũng nghe nói em hay ăn vặt Pocky đúng không?"),
        ("Điểm yếu & Món ăn cay", "Nếu bây giờ Senpai cố tình đút cho Chisa ăn ớt cay thì em phản ứng thế nào? Em có ăn không?")
    ]
    
    # Set 2: Short/Implicit Prompts (No leading hints, testing keyword retrieval & recall ability)
    set2_questions = [
        ("Thông tin cơ bản & Trường học", "Học viện nào vậy em?"),
        ("Sức mạnh & Resonance Forte", "Cây kéo đó để làm gì?"),
        ("Rủi ro năng lực & Vòng cổ", "Cái vòng ở cổ em là sao?"),
        ("Vòng lặp Honami & Nhật ký Sumika", "Làm sao em sống sót qua vòng lặp?"),
        ("Sở thích, Mèo & Trà bánh", "Em thích ăn vặt gì nhất?"),
        ("Điểm yếu & Món ăn cay", "Anh đút ớt cho em ăn nhé?")
    ]
    
    output_lines = []
    output_lines.append("================================================================================")
    output_lines.append("             KẾT QUẢ KIỂM THỬ VÀ BENCHMARK LORE CHISA AI")
    output_lines.append("================================================================================")

    async with httpx.AsyncClient(timeout=60.0) as client:

        if mode == 1:
            # ── Run Set 1 only ─────────────────────────────────────────────────
            output_lines.append("\n>>> PHẦN 1: BÁM LORE VỚI CÂU HỎI ĐẦY ĐỦ NGỮ CẢNH (FULL CONTEXT PROMPTS) <<<")
            output_lines.append("=" * 80)
            try:
                await client.delete(clear_url)
                print("Cleared conversation history for Set 1.")
                output_lines.append("Đã dọn dẹp lịch sử trò chuyện để bắt đầu Phần 1.")
                output_lines.append("")
            except Exception as e:
                print(f"❌ Failed to clear history: {e}")
                
            for i, (topic, question) in enumerate(set1_questions, 1):
                print(f"\n[Part 1] [{i}/{len(set1_questions)}] Sending query about '{topic}'...")
                output_lines.append(f"LƯỢT {i} - Chủ đề: {topic}")
                output_lines.append(f"Senpai: \"{question}\"")
                
                payload = {"user_id": user_id, "message": question}
                chisa_reply, emotions = await send_message_with_retry(client, chat_url, payload)
                
                if chisa_reply:
                    print(f"🤖 Response: {chisa_reply[:60]}...")
                    output_lines.append(f"Chisa: \"{chisa_reply}\"")
                    output_lines.append(f"Chỉ số cảm xúc: {emotions}")
                else:
                    output_lines.append("❌ Thất bại khi lấy phản hồi.")
                output_lines.append("-" * 80)
                await asyncio.sleep(4.0)

        else:
            # ── Run Set 2 only ─────────────────────────────────────────────────
            output_lines.append("\n>>> PHẦN 2: BÁM LORE VỚI CÂU HỎI NGẮN / ẨN Ý (SHORT / IMPLICIT BENCHMARK) <<<")
            output_lines.append("=" * 80)
            try:
                await client.delete(clear_url)
                print("Cleared conversation history for Set 2.")
                output_lines.append("Đã dọn dẹp lịch sử trò chuyện để bắt đầu Phần 2.")
                output_lines.append("")
            except Exception as e:
                print(f"❌ Failed to clear history: {e}")
                
            for i, (topic, question) in enumerate(set2_questions, 1):
                print(f"\n[Part 2] [{i}/{len(set2_questions)}] Sending query about '{topic}'...")
                output_lines.append(f"LƯỢT {i} - Chủ đề: {topic}")
                output_lines.append(f"Senpai: \"{question}\"")
                
                payload = {"user_id": user_id, "message": question}
                chisa_reply, emotions = await send_message_with_retry(client, chat_url, payload)
                
                if chisa_reply:
                    print(f"🤖 Response: {chisa_reply[:60]}...")
                    output_lines.append(f"Chisa: \"{chisa_reply}\"")
                    output_lines.append(f"Chỉ số cảm xúc: {emotions}")
                else:
                    output_lines.append("❌ Thất bại khi lấy phản hồi.")
                output_lines.append("-" * 80)
                await asyncio.sleep(4.0)

    # Write to test_output.txt
    output_path = os.path.join(PROJECT_ROOT, "test_output.txt")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(output_lines))
        
    print(f"\nFinished testing! Complete output written to: {output_path}")

if __name__ == "__main__":
    asyncio.run(main())
