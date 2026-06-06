import asyncio
import httpx
import sys
import os
import uuid

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

async def main():
    user_id = await get_test_user_id()
    chat_url = "http://localhost:8000/api/v1/chat"
    clear_url = f"http://localhost:8000/api/v1/chat/clear/{user_id}"
    
    # Define 6 test prompts that cover all essential aspects of Chisa's lore
    questions = [
        ("Thông tin cơ bản & Trường học", "Chào em Chisa, em giới thiệu bản thân một chút và kể cho anh nghe về trường em đang học đi nhé!"),
        ("Sức mạnh & Resonance Forte", "Anh tò mò về năng lực Resonance đặc biệt của em. Cây kéo khổng lồ đó hoạt động ra sao và em nhìn thấy những gì?"),
        ("Rủi ro năng lực & Vòng cổ", "Tại sao em lại phải đeo một thiết bị ở cổ vậy? Có phải liên quan đến rủi ro Overclocking không em?"),
        ("Vòng lặp Honami & Nhật ký Sumika", "Kể cho anh nghe về khoảng thời gian em bị kẹt ở Honami đi, và cuốn nhật ký của chị Sumika đã giúp ích gì cho em vậy?"),
        ("Sở thích, Mèo & Trà bánh", "Em có sở thích gì đặc biệt không, ví dụ như nuôi mèo hay làm trà bánh gì đó? Anh cũng nghe nói em hay ăn vặt Pocky đúng không?"),
        ("Điểm yếu & Món ăn cay", "Nếu bây giờ Senpai cố tình đút cho Chisa ăn ớt cay thì em phản ứng thế nào? Em có ăn không?")
    ]
    
    output_lines = []
    output_lines.append("================================================================================")
    output_lines.append("                KẾT QUẢ KIỂM THỬ VÉT TOÀN BỘ LORE CHISA AI")
    output_lines.append("================================================================================")
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            # Clear history first to isolate test run
            await client.delete(clear_url)
            print("Cleared conversation history for test user.")
            output_lines.append("Đã dọn dẹp lịch sử trò chuyện để bắt đầu cuộc hội thoại mới.")
            output_lines.append("")
        except Exception as e:
            print(f"❌ Failed to clear history: {e}")
            
        for i, (topic, question) in enumerate(questions, 1):
            print(f"\n[{i}/6] Sending query about '{topic}'...")
            output_lines.append(f"LƯỢT {i} - Chủ đề: {topic}")
            output_lines.append(f"Senpai: \"{question}\"")
            
            payload = {
                "user_id": user_id,
                "message": question
            }
            
            # Robust retry loop to survive standard/free tier Gemini API rate limits (15 RPM)
            max_retries = 4
            backoff_delay = 5.0
            response_data = None
            
            for attempt in range(1, max_retries + 1):
                try:
                    response = await client.post(chat_url, json=payload)
                    if response.status_code == 429 or response.status_code == 500:
                        print(f"  [!] Received status {response.status_code} (Rate Limit/Server overload), retrying in {backoff_delay}s... (Attempt {attempt}/{max_retries})")
                        await asyncio.sleep(backoff_delay)
                        backoff_delay *= 2.0
                        continue
                        
                    response.raise_for_status()
                    response_data = response.json()
                    break
                except Exception as e:
                    print(f"  [!] Attempt {attempt} failed: {e}")
                    if attempt < max_retries:
                        print(f"  Retrying in {backoff_delay}s...")
                        await asyncio.sleep(backoff_delay)
                        backoff_delay *= 2.0
                    else:
                        response_data = {"error": str(e)}
            
            if response_data and "response" in response_data:
                chisa_reply = response_data.get("response", "")
                emotions = response_data.get("emotions", {})
                
                print(f"🤖 Response: {chisa_reply[:60]}...")
                output_lines.append(f"Chisa: \"{chisa_reply}\"")
                output_lines.append(f"Chỉ số cảm xúc hiện tại: {emotions}")
                output_lines.append("-" * 80)
            else:
                err_msg = f"❌ Thất bại sau {max_retries} lần thử: {response_data}"
                print(err_msg)
                output_lines.append(err_msg)
                output_lines.append("-" * 80)
                
            # Decent sleep between turns to stay well within rate limits
            print("Sleeping 4.0s before next turn to prevent rate limits...")
            await asyncio.sleep(4.0)
            
    # Write to test_output.txt
    output_path = os.path.join(PROJECT_ROOT, "test_output.txt")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(output_lines))
        
    print(f"\nFinished testing! Complete output written to: {output_path}")

if __name__ == "__main__":
    asyncio.run(main())
