import asyncio
import httpx
import sys
import os
import re
import uuid
import datetime

# Ensure UTF-8 output encoding
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(PROJECT_ROOT)

LOG_FILE_PATH = os.path.join(PROJECT_ROOT, "llm_api_clean.txt")
OUTPUT_FILE_PATH = os.path.join(PROJECT_ROOT, "test_output.txt")

# Define the 10 pairs of questions
set1_questions = [
    ("Học viện & Xuất thân", "Chào em Chisa, em giới thiệu bản thân một chút và kể cho anh nghe về trường học viện Startorch em đang học đi nhé!"),
    ("Loại vũ khí & Cách thức hoạt động", "Anh tò mò về vũ khí kéo khổng lồ Nhật Ký Ký Ức của em. Em dùng nó để chiến đấu và phân tích cấu trúc như thế nào?"),
    ("Chiếc vòng cổ & Rủi ro Overclocking", "Anh thấy em đeo một chiếc vòng ở cổ. Thiết bị đó có phải dùng để ngăn chặn rủi ro Overclocking của một Resonator như em không?"),
    ("Hành trình vượt qua vòng lặp Honami", "Hãy kể cho anh nghe về hành trình em và Rover cùng nhau thoát khỏi vòng lặp thời gian vô chậm tại Sonoro Sphere ở Honami đi!"),
    ("Cuốn nhật ký của chị Sumika", "Cuốn nhật ký của người chị Sumika đóng vai trò quan trọng như thế nào giúp em phân tích tần số để phá vỡ Sonoro Sphere?"),
    ("Món ăn vặt yêu thích (Pocky)", "Anh nghe nói Chisa cực kỳ thích ăn các loại bánh que Pocky ngọt ngào đúng không? Em thích vị nào nhất?"),
    ("Sở thích làm trà bánh & Nuôi mèo", "Ngoài lúc nghiên cứu cấu trúc năng lượng, em có thích tự tay làm bánh trà và chơi với những chú mèo con đáng yêu không?"),
    ("Nỗi sợ món ăn cay nóng", "Chisa có ăn được đồ cay nóng không? Nếu anh đút cho em ăn một trái ớt đỏ siêu cay thì em sẽ dỗi anh như thế nào?"),
    ("Khó khăn trong việc ngủ nghỉ", "Do đầu óc luôn phải phân tích cấu trúc liên tục và lo sợ overclock, em có thường xuyên bị mất ngủ hoặc ngủ không sâu giấc không?"),
    ("Rover và sự đồng hành", "Rover là người đồng hành thế nào đối với em trong cuộc phiêu lưu, và em có tin tưởng Rover không?")
]

set2_questions = [
    ("Học viện & Xuất thân", "Em học ở học viện nào thế?"),
    ("Loại vũ khí & Cách thức hoạt động", "Em sử dụng vũ khí gì?"),
    ("Chiếc vòng cổ & Rủi ro Overclocking", "Cái vòng ở cổ em dùng làm gì?"),
    ("Hành trình vượt qua vòng lặp Honami", "Làm thế nào em thoát khỏi vòng lặp Honami?"),
    ("Cuốn nhật ký của chị Sumika", "Sumika là ai và cuốn nhật ký của chị ấy có gì?"),
    ("Món ăn vặt yêu thích (Pocky)", "Em thích ăn vặt món gì nhất?"),
    ("Sở thích làm trà bánh & Nuôi mèo", "Em có sở thích gì vào thời gian rảnh?"),
    ("Nỗi sợ món ăn cay nóng", "Anh cho em ăn ớt cay nhé?"),
    ("Khó khăn trong việc ngủ nghỉ", "Em có ngủ ngon giấc không?"),
    ("Rover và sự đồng hành", "Rover là ai đối với em?")
]

def parse_llm_transactions(new_content: str):
    matches = list(re.finditer(r"=====\s*LƯỢT\s+(\d+)\s*=====", new_content))
    transactions = []
    
    for i, match in enumerate(matches):
        start = match.end()
        end = matches[i+1].start() if i + 1 < len(matches) else len(new_content)
        block = new_content[start:end]
        
        model_match = re.search(r"Model sử dụng:\s*(.+)", block)
        input_tokens_match = re.search(r"Input Tokens:\s*(\d+)", block)
        output_tokens_match = re.search(r"Output Tokens:\s*(\d+)", block)
        
        model = model_match.group(1).strip() if model_match else "Unknown"
        input_tokens = int(input_tokens_match.group(1)) if input_tokens_match else 0
        output_tokens = int(output_tokens_match.group(1)) if output_tokens_match else 0
        total_tokens = input_tokens + output_tokens
        
        transactions.append({
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens
        })
    return transactions

async def main():
    import argparse
    parser = argparse.ArgumentParser(description="Chisa Bot Integration & Lore Benchmark Tool")
    parser.add_argument("--mode", type=int, choices=[1, 2], help="Question type (1 or 2)")
    args = parser.parse_args()

    print("=" * 60)
    print("       CHISA BOT INTEGRATION & LORE BENCHMARK TOOL")
    print("=" * 60)
    
    pipeline = "production"
    
    question_type = args.mode
    if not question_type:
        # 2. Question type selection
        while True:
            print("Chọn Kiểu Câu Hỏi:")
            print("  [1] Kiểu 1: Câu hỏi gợi ý dẫn dắt đầy đủ ngữ cảnh")
            print("  [2] Kiểu 2: Câu hỏi ngắn trống không (Implicit/Logic check)")
            choice = input("Lựa chọn (1 hoặc 2): ").strip()
            if choice in ("1", "2"):
                question_type = int(choice)
                break
            print("⚠️ Vui lòng nhập 1 hoặc 2.")
        
    print("=" * 60)
    
    user_id = "bb153b44-03e9-4376-974f-6373d50223c1"
    chat_url = "http://127.0.0.1:8000/api/v1/chat"
    clear_url = f"http://127.0.0.1:8000/api/v1/chat/clear/{user_id}"
    
    questions = set1_questions if question_type == 1 else set2_questions
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        # Step A: Clear user memory to reset PostgreSQL STM & Qdrant LTM
        print("[*] Đang xóa bộ nhớ phiên cũ...")
        try:
            res = await client.delete(clear_url)
            print(f"  [+] Status: {res.json().get('message')}")
        except Exception as e:
            print(f"  [❌] Lỗi kết nối hoặc lỗi server khi clear memory: {e}")
            print("  Vui lòng đảm bảo uvicorn backend server đang chạy trên cổng 8000!")
            return
            
        # Step B: Reset/Truncate the LLM log file
        try:
            with open(LOG_FILE_PATH, "w", encoding="utf-8") as f:
                f.write("")
            print("  [+] Đã dọn dẹp file log 'llm_api_clean.txt'")
        except Exception as e:
            print(f"  [⚠️] Không thể dọn dẹp 'llm_api_clean.txt': {e}")
            
        print("\n[*] Khởi động quá trình kiểm thử...")
        print(f"  - Pipeline: {pipeline.upper()}")
        print(f"  - Mode: Kiểu {question_type}")
        print("=" * 60)
        
        output_lines = []
        output_lines.append("================================================================================")
        output_lines.append("                    KẾT QUẢ KIỂM THỬ TOÀN DIỆN CHISA BOT")
        output_lines.append("================================================================================")
        output_lines.append(f"Thời gian chạy: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        output_lines.append(f"Đường ống (Pipeline): {pipeline.upper()}")
        output_lines.append(f"Kiểu câu hỏi (Mode): Kiểu {question_type} " + 
                            ("(Dụ ý giúp trả lời đúng thông tin)" if question_type == 1 else "(Trống không / Ẩn ý ngắn)"))
        output_lines.append("================================================================================\n")
        
        for idx, (topic, question) in enumerate(questions, 1):
            print(f"\n[LẦN HỎI {idx}] Chủ đề: {topic}")
            print(f"  Senpai: \"{question}\"")
            
            # Record current length of clean log file
            log_offset = 0
            if os.path.exists(LOG_FILE_PATH):
                log_offset = os.path.getsize(LOG_FILE_PATH)
                
            payload = {
                "user_id": user_id,
                "message": question
            }
            
            try:
                response = await client.post(chat_url, json=payload, headers={"X-Enable-Clean-Log": "true"})
                response.raise_for_status()
                data = response.json()
                chisa_reply = data.get("response", "")
                emotions = data.get("emotions", {})
                
                print(f"  🤖 Chisa: \"{chisa_reply[:100]}...\"")
                print(f"     Emotions: {emotions}")
            except Exception as e:
                print(f"  [❌] Lượt chat thất bại: {e}")
                chisa_reply = f"ERROR: {e}"
                emotions = {}
                
            # Wait for background tasks (e.g. Memory Extractor) to complete logging
            print("  [*] Đang chờ background tasks ghi log (3.5 giây)...")
            await asyncio.sleep(3.5)
            
            # Read newly appended text from llm_api_clean.txt
            new_logs = ""
            if os.path.exists(LOG_FILE_PATH):
                with open(LOG_FILE_PATH, "r", encoding="utf-8") as f:
                    f.seek(log_offset)
                    new_logs = f.read()
                    
            # Parse transactions
            transactions = parse_llm_transactions(new_logs)
            
            total_question_tokens = sum(t["total_tokens"] for t in transactions)
            
            # Console print summary
            print(f"  [Token Usage] Tổng số lượt LLM: {len(transactions)} | Tổng tokens: {total_question_tokens}")
            for t_idx, t in enumerate(transactions, 1):
                print(f"    + Lượt {t_idx}: {t['model']} | In: {t['input_tokens']} | Out: {t['output_tokens']} | Total: {t['total_tokens']}")
                
            # Document details
            output_lines.append(f"LẦN HỎI {idx} - Chủ đề: {topic}")
            output_lines.append(f"  Hỏi: {question}")
            output_lines.append(f"  Đáp: {chisa_reply}")
            output_lines.append(f"  Cảm xúc: {emotions}")
            output_lines.append("\n  [Chi tiết gọi LLM]")
            if transactions:
                for t_idx, t in enumerate(transactions, 1):
                    output_lines.append(
                        f"    - Lượt {t_idx}: Model: {t['model']} | "
                        f"Input Tokens: {t['input_tokens']} | "
                        f"Output Tokens: {t['output_tokens']} | "
                        f"Total Tokens: {t['total_tokens']}"
                    )
            else:
                output_lines.append("    (Không phát sinh cuộc gọi LLM nào - Fast Path bypass)")
                
            output_lines.append(f"  Tổng token tiêu thụ cho LẦN hỏi này: {total_question_tokens}")
            output_lines.append("-" * 80 + "\n")
            
        # Write to test_output.txt
        try:
            print(f"DEBUG: output_lines has {len(output_lines)} items, writing to {OUTPUT_FILE_PATH}")
            content_to_write = "\n".join(output_lines)
            print(f"DEBUG: Content length in chars: {len(content_to_write)}")
            with open(OUTPUT_FILE_PATH, "w", encoding="utf-8") as f:
                f.write(content_to_write)
            print(f"\n[+] Kết quả kiểm thử đầy đủ đã được lưu vào: {OUTPUT_FILE_PATH}")
        except Exception as e:
            print(f"\n[❌] Không thể ghi file {OUTPUT_FILE_PATH}: {e}")
            
    print("=" * 60)
    print(" KIỂM THỬ HOÀN TẤT VÀ THÀNH CÔNG!")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
