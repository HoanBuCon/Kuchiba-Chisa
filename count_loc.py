import os

def count_lines_of_code(directory):
    # Các đuôi file mã nguồn muốn đếm
    valid_extensions = ('.py', '.js', '.jsx', '.html', '.css', '.md', '.yml', '.yaml', '.sql')
    
    # Các thư mục muốn bỏ qua
    ignore_dirs = {'.git', 'venv', 'node_modules', '__pycache__', '.pytest_cache', 'dist', 'build', '.env'}
    
    total_lines = 0
    total_files = 0
    
    for root, dirs, files in os.walk(directory):
        # Loại bỏ các thư mục ignore khỏi vòng lặp os.walk
        dirs[:] = [d for d in dirs if d not in ignore_dirs]
        
        for file in files:
            if file.endswith(valid_extensions):
                filepath = os.path.join(root, file)
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        lines = f.readlines()
                        total_lines += len(lines)
                        total_files += 1
                except UnicodeDecodeError:
                    # Bỏ qua nếu không đọc được bằng utf-8 (file nhị phân, ảnh...)
                    pass
                except Exception as e:
                    print(f"Lỗi khi đọc file {filepath}: {e}")
                    
    return total_files, total_lines

if __name__ == "__main__":
    current_dir = os.getcwd()
    files, lines = count_lines_of_code(current_dir)
    print("=" * 40)
    print(f"Thống kê mã nguồn tại: {current_dir}")
    print(f"Tổng số file: {files:,}")
    print(f"Tổng số dòng code: {lines:,}")
    print("=" * 40)
