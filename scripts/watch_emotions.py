import time
import os
import sys
import asyncio

# Thêm đường dẫn project vào sys.path để có thể import các thư mục con
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from app.config.settings import settings

def clear_console():
    os.system('cls' if os.name == 'nt' else 'clear')

async def main():
    # Sử dụng nguyên gốc asyncpg đã có sẵn trong dự án thay vì psycopg2
    db_url = str(settings.DATABASE_URL)
    engine = create_async_engine(db_url)
    
    print("🌸 Đang kết nối tới trái tim của Chisa...")
    
    try:
        while True:
            clear_console()
            print("========================================================================================================")
            print("                              🌸 BẢNG THEO DÕI CẢM XÚC CHISA 🌸")
            print("========================================================================================================")
            print(f"{'User ID':<38} | {'Vui (Joy)':<10} | {'Buồn (Sad)':<10} | {'Tin Tưởng':<10} | {'Tức Giận':<10} | {'Gắn Kết':<10}")
            print("-" * 104)

            async with engine.connect() as conn:
                result = await conn.execute(text("SELECT user_id, joy, sadness, trust, irritation, attachment FROM emotion_state"))
                rows = result.fetchall()
                
                if not rows:
                    print(f"{'Chưa có người dùng nào tương tác...':^104}")
                else:
                    for row in rows:
                        uid = str(row.user_id)
                        joy = f"{row.joy:.2f}"
                        sad = f"{row.sadness:.2f}"
                        trust = f"{row.trust:.2f}"
                        mad = f"{row.irritation:.2f}"
                        att = f"{row.attachment:.2f}"
                        print(f"{uid:<38} | {joy:<10} | {sad:<10} | {trust:<10} | {mad:<10} | {att:<10}")

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
        print("\n[!] Đã dừng theo dõi cảm xúc.")
