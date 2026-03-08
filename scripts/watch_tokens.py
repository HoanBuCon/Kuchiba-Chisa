import time
import os
import sys
import asyncio

# Add project path to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from app.config.settings import settings

def clear_console():
    os.system('cls' if os.name == 'nt' else 'clear')

async def main():
    db_url = str(settings.DATABASE_URL)
    engine = create_async_engine(db_url)
    
    print("🤖 Đang kết nối tới Trung tâm giám sát Token...")
    
    try:
        while True:
            clear_console()
            print("========================================================================================================")
            print("                              💳 BẢNG THEO DÕI TOKEN TIÊU THỤ (LTM + STM) 💳")
            print("========================================================================================================")
            print(f"{'Thời gian':<20} | {'User ID':<36} | {'Tokens':<8} | {'Nội dung tin nhắn (Snippets)'}")
            print("-" * 104)

            async with engine.connect() as conn:
                # Query the latest 10 assistant responses that have a token count
                query = """
                SELECT 
                    created_at, 
                    user_id, 
                    token_count, 
                    content 
                FROM messages 
                WHERE role = 'ASSISTANT' AND token_count IS NOT NULL 
                ORDER BY created_at DESC 
                LIMIT 10
                """
                result = await conn.execute(text(query))
                rows = result.fetchall()
                
                if not rows:
                    print(f"{'Chưa có dữ liệu token nào được ghi nhận...':^104}")
                else:
                    for row in rows:
                        time_str = row.created_at.strftime("%H:%M:%S") if row.created_at else "N/A"
                        uid = str(row.user_id)
                        tokens = str(row.token_count)
                        
                        # Prepare snippet
                        content = row.content.replace('\n', ' ')
                        snippet = content[:35] + "..." if len(content) > 35 else content
                        
                        print(f"{time_str:<20} | {uid:<36} | {tokens:<8} | {snippet}")

            print("========================================================================================================")
            print("Nhấn Ctrl+C để thoát. Đang tự động làm mới sau mỗi 2 giây...")
            await asyncio.sleep(2)
            
    except asyncio.CancelledError:
        pass
    except Exception as e:
        print(f"\n[X] Lỗi kết nối: {e}")
    finally:
        await engine.dispose()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[!] Đã dừng theo dõi Token.")
