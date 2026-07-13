import os
import subprocess
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

def run_pygount_and_analyze(directory):
    print(f"Đang phân tích mã nguồn bằng pygount tại {directory}...")
    print("Vui lòng đợi giây lát, quá trình phân tích AST có thể mất vài giây...\n")
    
    # Cấu hình các thư mục cần bỏ qua
    folders_to_skip = "venv,node_modules,.git,__pycache__,alembic_migrations,logs,scratch,.pytest_cache,dist,build,.mypy_cache"
    
    try:
        # Gọi subprocess lấy kết quả JSON thẳng vào stdout
        # Sử dụng tham số --format=json
        pygount_exe = os.path.join("venv", "Scripts", "pygount.exe")
        if not os.path.exists(pygount_exe):
            print("Lỗi: Không tìm thấy thư viện pygount. Hãy chạy lệnh sau trước:")
            print("pip install pygount")
            sys.exit(1)
            
        result = subprocess.run(
            [pygount_exe, "--format=json", f"--folders-to-skip={folders_to_skip}", directory],
            capture_output=True,
            text=True,
            encoding='utf-8',
            check=True
        )
    except subprocess.CalledProcessError as e:
        print(f"Lỗi khi chạy pygount: {e.stderr}")
        sys.exit(1)
        
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        print("Lỗi: Không thể phân tích kết quả JSON từ pygount.")
        sys.exit(1)
        
    files = data.get("files", [])
    
    # Khởi tạo các nhóm thống kê
    stats = {
        "core_rag": {"code": 0, "comment": 0, "empty": 0, "files": 0},
        "discord_bot": {"code": 0, "comment": 0, "empty": 0, "files": 0},
        "web_ui": {"code": 0, "comment": 0, "empty": 0, "files": 0},
        "total": {"code": 0, "comment": 0, "empty": 0, "files": 0}
    }
    
    for f in files:
        # Bỏ qua các file không đếm được (vd binary) hoặc unknown
        if not f.get("isCountable") or f.get("state") != "analyzed":
            continue
            
        path = f.get("path", "").replace("\\", "/")
        
        # Lọc sạch hoàn toàn các file Markdown, JSON, TXT, YAML để không bị tính vào Comment
        if path.endswith(('.md', '.json', '.txt', '.yaml', '.yml', '.toml', '.ini', '.csv')):
            continue
        code = f.get("codeCount", 0)
        comment = f.get("documentationCount", 0)
        empty = f.get("emptyCount", 0)
        
        # Phân loại nhóm
        category = "core_rag"
        
        if "discord/" in path:
            category = "discord_bot"
        elif "app/interface/api/templates/" in path or "app/interface/api/static/" in path or ".html" in path or ".css" in path:
            category = "web_ui"
            
        # Cộng dồn vào nhóm
        stats[category]["code"] += code
        stats[category]["comment"] += comment
        stats[category]["empty"] += empty
        stats[category]["files"] += 1
        
        # Cộng dồn tổng
        stats["total"]["code"] += code
        stats["total"]["comment"] += comment
        stats["total"]["empty"] += empty
        stats["total"]["files"] += 1

    return stats

def print_stats(stats):
    print("="*60)
    print(" BÁO CÁO THỐNG KÊ MÃ NGUỒN (CHÍNH XÁC BẰNG PYGOUNT)")
    print("="*60)
    
    def print_category(name, data):
        total_lines = data['code'] + data['comment'] + data['empty']
        print(f" 📂 {name.upper()} (Quét được {data['files']:,} files)")
        print("-" * 60)
        print(f"   🟩 Code logic thực tế: {data['code']:>8,}")
        print(f"   🟧 Chú thích/Docstring:{data['comment']:>8,}")
        print(f"   ⬜ Dòng trống:         {data['empty']:>8,}")
        print(f"   📊 TỔNG CỘNG:          {total_lines:>8,} dòng")
        print("-" * 60)
        
    print_category("Core RAG (AI Backend)", stats["core_rag"])
    print_category("Discord Bot (NodeJS)", stats["discord_bot"])
    print_category("Web UI (Giao diện web)", stats["web_ui"])
    
    print("="*60)
    print_category("TỔNG CỘNG TOÀN DỰ ÁN", stats["total"])
    print("="*60)

if __name__ == "__main__":
    current_dir = os.getcwd()
    stats = run_pygount_and_analyze(current_dir)
    print_stats(stats)
