import os
import sys
import time
import subprocess
import urllib.request
import webbrowser
import atexit
import signal
import threading

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(ROOT_DIR, "frontend")
DISCORD_DIR = os.path.join(ROOT_DIR, "discord")

def find_virtualenv_python() -> str:
    """
    100% Foolproof PEP 405 Standard Virtualenv Discovery:
    1. Check if current Python process is ALREADY in a venv (sys.prefix != sys.base_prefix).
    2. According to PEP 405, EVERY virtual environment MUST contain a 'pyvenv.cfg' file.
       We scan for 'pyvenv.cfg' to guarantee 100% accuracy regardless of folder name.
    """
    # 1. Official runtime check: if already executing inside ANY venv
    if sys.prefix != sys.base_prefix or "VIRTUAL_ENV" in os.environ:
        return os.path.abspath(sys.executable)

    # 2. Fast check common folder names first
    common_names = ["venv", ".venv", "env", ".env_py", "virtualenv"]
    for name in common_names:
        candidate_dir = os.path.join(ROOT_DIR, name)
        py_exe = os.path.join(candidate_dir, "Scripts", "python.exe") if os.name == 'nt' else os.path.join(candidate_dir, "bin", "python")
        if os.path.exists(py_exe) and os.path.exists(os.path.join(candidate_dir, "pyvenv.cfg")):
            return os.path.abspath(py_exe)

    # 3. Standard PEP 405 scan: Search workspace for any folder containing 'pyvenv.cfg'
    try:
        for root, dirs, files in os.walk(ROOT_DIR):
            # Skip irrelevant subtrees for maximum speed
            dirs[:] = [d for d in dirs if d not in ('node_modules', '.git', '__pycache__', 'frontend', 'discord', 'data')]
            if 'pyvenv.cfg' in files:
                py_exe = os.path.join(root, "Scripts", "python.exe") if os.name == 'nt' else os.path.join(root, "bin", "python")
                if os.path.exists(py_exe):
                    return os.path.abspath(py_exe)
    except Exception:
        pass

    return os.path.abspath(sys.executable)

VENV_PYTHON = find_virtualenv_python()

# ── Auto-Activate Virtualenv ─────────────────────────────────────────
if os.path.exists(VENV_PYTHON):
    current_python = os.path.abspath(sys.executable)
    if current_python.lower() != VENV_PYTHON.lower() and "VIRTUAL_ENV" not in os.environ:
        os.environ["VIRTUAL_ENV"] = os.path.dirname(os.path.dirname(VENV_PYTHON))
        venv_scripts = os.path.dirname(VENV_PYTHON)
        os.environ["PATH"] = venv_scripts + os.pathsep + os.environ.get("PATH", "")
        os.execv(VENV_PYTHON, [VENV_PYTHON] + sys.argv)

# ── Ensure Windows ANSI & Console Setup ─────────────────────────────
if os.name == 'nt':
    import msvcrt
    os.system('')  # Enable ANSI escape sequences in Windows CMD/PowerShell

# Global list of PIDs spawned by this CLI session
SPAWNED_PIDS = set()

# ── Colors & Styles ──────────────────────────────────────────────────
C_RESET   = "\033[0m"
C_BOLD    = "\033[1m"
C_RED     = "\033[31m"
C_GREEN   = "\033[32m"
C_YELLOW  = "\033[33m"
C_BLUE    = "\033[34m"
C_MAGENTA = "\033[35m"
C_CYAN    = "\033[36m"
C_GRAY    = "\033[90m"
C_BG_RED  = "\033[41m\033[37m"
C_BG_GRAY = "\033[47m\033[30m"

# ── Helper Functions ─────────────────────────────────────────────────

# ── Status Cache Globals ──────────────────────────────────────────────
LAST_STATUS_CACHE = None
LAST_STATUS_TIME = 0.0

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def check_port_listening(port: int) -> bool:
    """Check if a port is currently listening instantly via Python socket."""
    import socket
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.1)
            return s.connect_ex(('127.0.0.1', port)) == 0
    except Exception:
        return False

def check_url_health(url: str, timeout: float = 0.3) -> bool:
    """Check if a URL responds with HTTP 200."""
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'ChisaCLI/1.0'})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False

def check_discord_process() -> bool:
    """Check if Discord bot process (node.exe running in discord directory) is running."""
    if os.name == 'nt':
        try:
            res = subprocess.check_output('wmic process where "name=\'node.exe\'" get commandline', shell=True, stderr=subprocess.DEVNULL).decode('utf-8', errors='ignore')
            return 'discord' in res.lower()
        except Exception:
            return False
    return False

def kill_process_tree_by_pid(pid: int):
    """Terminate a process and all its child processes."""
    if os.name == 'nt':
        subprocess.run(f"taskkill /F /T /PID {pid}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        subprocess.run(f"kill -9 {pid}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def kill_processes_by_name(name_pattern: str):
    """Kill processes matching name (e.g. python, node)."""
    if os.name == 'nt':
        try:
            procs = subprocess.check_output(f"wmic process where \"name like '%{name_pattern}%'\" get processid", shell=True, stderr=subprocess.DEVNULL).decode('utf-8', errors='ignore')
            for line in procs.strip().split('\n')[1:]:
                line = line.strip()
                if line.isdigit() and int(line) != os.getpid():
                    kill_process_tree_by_pid(int(line))
        except Exception:
            pass

def kill_process_on_port(port: int):
    """Find and kill processes listening on specified port."""
    if os.name == 'nt':
        try:
            cmd = f"netstat -ano | findstr LISTENING | findstr :{port}"
            output = subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL).decode('utf-8', errors='ignore')
            pids = set()
            for line in output.strip().split('\n'):
                parts = line.strip().split()
                if len(parts) >= 5:
                    pids.add(parts[-1])
            for pid in pids:
                if pid.isdigit() and int(pid) != 0 and int(pid) != os.getpid():
                    kill_process_tree_by_pid(int(pid))
        except Exception:
            pass

def cleanup_all_spawned():
    """Cleanup all processes launched during CLI session on exit."""
    if SPAWNED_PIDS:
        print(f"\n{C_YELLOW}[CLI Cleanup] Dang dọn dẹp các tiến trình đã khởi chạy trong session...{C_RESET}")
        for pid in list(SPAWNED_PIDS):
            kill_process_tree_by_pid(pid)
        SPAWNED_PIDS.clear()

atexit.register(cleanup_all_spawned)

def signal_handler(sig, frame):
    cleanup_all_spawned()
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# ── Launch Helpers ───────────────────────────────────────────────────

def ensure_docker_containers():
    """Ensure Postgres, Redis, Qdrant containers are running via docker-compose."""
    print(f"\n{C_YELLOW}[Docker] Đang kiểm tra và khởi động các Container (Postgres, Redis, Qdrant)...{C_RESET}")
    cmd = "docker-compose up -d postgres redis qdrant"
    try:
        subprocess.run(cmd, cwd=ROOT_DIR, shell=True, check=True)
        print(f"{C_GREEN}[Docker] Container sẵn sàng!{C_RESET}")
        time.sleep(1.5)
        return True
    except Exception as e:
        print(f"{C_RED}[Docker] Lỗi khởi động Docker Containers: {e}{C_RESET}")
        print(f"{C_GRAY}Hãy đảm bảo Docker Desktop đang chạy.{C_RESET}")
        time.sleep(3)
        return False

def launch_backend() -> bool:
    """Launch Backend Core RAG in a new window."""
    if check_port_listening(8000):
        print(f"{C_GREEN}[Backend] Backend Core RAG đã đang chạy trên port 8000!{C_RESET}")
        time.sleep(1.5)
        return True

    if not ensure_docker_containers():
        return False

    print(f"{C_YELLOW}[Backend] Đang khởi chạy Backend Core RAG trên cửa sổ mới...{C_RESET}")
    venv_dir = os.path.dirname(os.path.dirname(VENV_PYTHON))
    ps_script = (
        f"$host.UI.RawUI.WindowTitle='[CHISA BACKEND CORE RAG]'; "
        f"cd '{ROOT_DIR}'; "
        f"Write-Host '[ CHISA BACKEND CORE RAG ]' -ForegroundColor Red; "
        f"& '{VENV_PYTHON}' -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"
    )
    cmd = f'start powershell -NoExit -Command "{ps_script}"'
    proc = subprocess.Popen(cmd, shell=True)
    SPAWNED_PIDS.add(proc.pid)
    
    print(f"{C_GRAY}Đang chờ Backend khởi động (max 15s)...{C_RESET}")
    for _ in range(15):
        if check_url_health("http://localhost:8000/health"):
            print(f"{C_GREEN}[Backend] Backend sẵn sàng tại http://localhost:8000!{C_RESET}")
            time.sleep(1.5)
            return True
        time.sleep(1.0)
    
    print(f"{C_YELLOW}[Backend] Backend đang khởi động, vui lòng kiểm tra cửa sổ mới.{C_RESET}")
    time.sleep(2)
    return True

def launch_frontend():
    """Launch Frontend (Vite) in a new window."""
    if check_port_listening(5173) or check_port_listening(5174):
        print(f"{C_GREEN}[Frontend] Frontend đã đang chạy trên port 5173/5174!{C_RESET}")
        time.sleep(1.5)
        return

    print(f"{C_YELLOW}[Frontend] Đang khởi chạy Frontend Vite trên cửa sổ mới...{C_RESET}")
    ps_script = (
        f"$host.UI.RawUI.WindowTitle='[CHISA FRONTEND VITE]'; "
        f"cd '{FRONTEND_DIR}'; "
        f"Write-Host '[ CHISA FRONTEND VITE ]' -ForegroundColor Cyan; "
        f"npm run dev"
    )
    cmd = f'start powershell -NoExit -Command "{ps_script}"'
    proc = subprocess.Popen(cmd, shell=True)
    SPAWNED_PIDS.add(proc.pid)
    print(f"{C_GREEN}[Frontend] Cửa sổ Frontend đã được mở.{C_RESET}")
    time.sleep(1.5)

def launch_discord():
    """Launch Discord Bot in a new window."""
    if check_discord_process():
        print(f"{C_GREEN}[Discord Bot] Bot Discord đã đang chạy!{C_RESET}")
        time.sleep(1.5)
        return

    print(f"{C_YELLOW}[Discord Bot] Đang khởi chạy Bot Discord trên cửa sổ mới...{C_RESET}")
    ps_script = (
        f"$host.UI.RawUI.WindowTitle='[CHISA DISCORD BOT]'; "
        f"cd '{DISCORD_DIR}'; "
        f"Write-Host '[ CHISA DISCORD BOT ]' -ForegroundColor Blue; "
        f"npm start"
    )
    cmd = f'start powershell -NoExit -Command "{ps_script}"'
    proc = subprocess.Popen(cmd, shell=True)
    SPAWNED_PIDS.add(proc.pid)
    print(f"{C_GREEN}[Discord Bot] Cửa sổ Discord Bot đã được mở.{C_RESET}")
    time.sleep(1.5)

def launch_visualizer():
    """Open Visualizer dashboard in browser (ensure backend running)."""
    print(f"{C_YELLOW}[Visualizer] Đang kiểm tra Backend trước khi mở Visualizer...{C_RESET}")
    if not check_url_health("http://localhost:8000/health"):
        print(f"{C_YELLOW}[Visualizer] Backend chưa chạy. Tiến hành khởi động Backend...{C_RESET}")
        if not launch_backend():
            return
    
    url = "http://localhost:8000/visualizer"
    print(f"{C_GREEN}[Visualizer] Đang mở trình duyệt tại {url}...{C_RESET}")
    webbrowser.open(url)
    time.sleep(1.5)

def launch_all():
    """Option 1: Launch Backend, Frontend, Discord Bot, and Visualizer."""
    print(f"\n{C_BOLD}{C_CYAN}🚀 ĐANG KHỞI ĐỘNG TOÀN BỘ HỆ THỐNG CHISA AI...{C_RESET}\n")
    if launch_backend():
        launch_frontend()
        launch_discord()
        launch_visualizer()
        print(f"\n{C_GREEN}{C_BOLD}✓ TOÀN BỘ TIẾN TRÌNH ĐÃ ĐƯỢC KHỞI CHẠY THÀNH CÔNG!{C_RESET}")
        time.sleep(2)

# ── Kill Handlers ────────────────────────────────────────────────────

def kill_all_services():
    """Kill all processes related to Chisa AI."""
    print(f"\n{C_RED}[Kill] Đang dừng toàn bộ tiến trình Chisa AI...{C_RESET}")
    kill_process_on_port(8000)
    kill_process_on_port(5173)
    kill_process_on_port(5174)
    kill_processes_by_name("node")
    kill_processes_by_name("python")
    print(f"{C_GREEN}[Kill] Đã dọn dẹp toàn bộ tiến trình!{C_RESET}")
    time.sleep(1.5)

def kill_backend_frontend_core():
    """Kill Backend & Frontend processes."""
    print(f"\n{C_RED}[Kill] Đang dừng Backend Core RAG & Frontend...{C_RESET}")
    kill_process_on_port(8000)
    kill_process_on_port(5173)
    kill_process_on_port(5174)
    print(f"{C_GREEN}[Kill] Đã dừng Backend & Frontend!{C_RESET}")
    time.sleep(1.5)

def kill_discord_bot():
    """Kill Discord Bot process specifically."""
    print(f"\n{C_RED}[Kill] Đang dừng Bot Discord...{C_RESET}")
    if os.name == 'nt':
        try:
            procs = subprocess.check_output("wmic process where \"name='node.exe' and commandline like '%discord%'\" get processid", shell=True, stderr=subprocess.DEVNULL).decode('utf-8', errors='ignore')
            for line in procs.strip().split('\n')[1:]:
                line = line.strip()
                if line.isdigit() and int(line) != os.getpid():
                    kill_process_tree_by_pid(int(line))
        except Exception:
            pass
    print(f"{C_GREEN}[Kill] Đã dừng Bot Discord!{C_RESET}")
    time.sleep(1.5)

def kill_visualizer():
    """Kill visualizer (Backend port 8000)."""
    print(f"\n{C_RED}[Kill] Đang đóng Visualizer (Dừng Backend 8000)...{C_RESET}")
    kill_process_on_port(8000)
    print(f"{C_GREEN}[Kill] Đã đóng Visualizer!{C_RESET}")
    time.sleep(1.5)

# ── Keyboard & Input Processing ─────────────────────────────────────

def read_key():
    """Read a single keypress, supporting Arrow keys, Enter, and Characters."""
    if os.name == 'nt':
        ch = msvcrt.getch()
        if ch in (b'\x00', b'\xe0'):
            ch2 = msvcrt.getch()
            if ch2 == b'H':
                return 'UP'
            elif ch2 == b'P':
                return 'DOWN'
            return 'OTHER'
        elif ch in (b'\r', b'\n'):
            return 'ENTER'
        elif ch == b'\x03':  # Ctrl+C
            raise KeyboardInterrupt
        else:
            try:
                return ch.decode('utf-8', errors='ignore')
            except Exception:
                return 'OTHER'
    else:
        # Fallback for Linux/macOS standard input
        import tty
        import termios
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(sys.stdin.fileno())
            ch = sys.stdin.read(1)
            if ch == '\x1b':
                ch2 = sys.stdin.read(2)
                if ch2 == '[A':
                    return 'UP'
                elif ch2 == '[B':
                    return 'DOWN'
            elif ch in ('\r', '\n'):
                return 'ENTER'
            return ch
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

# ── Menus & Rendering ────────────────────────────────────────────────

# ── Status Cache & Background Checker ────────────────────────────────
SYSTEM_STATUS = (f"{C_RED}🔴 CHECKING...{C_RESET}", f"{C_RED}🔴 CHECKING...{C_RESET}", f"{C_RED}🔴 CHECKING...{C_RESET}", f"{C_RED}🔴 CHECKING...{C_RESET}")
IS_FIRST_RENDER = True

def background_status_updater():
    global SYSTEM_STATUS
    while True:
        try:
            backend_ok = check_port_listening(8000)
            frontend_ok = check_port_listening(5173) or check_port_listening(5174)
            discord_ok = check_discord_process()
            visualizer_ok = backend_ok

            st_backend = f"{C_GREEN}🟢 ONLINE{C_RESET}" if backend_ok else f"{C_RED}🔴 OFFLINE{C_RESET}"
            st_frontend = f"{C_GREEN}🟢 ONLINE{C_RESET}" if frontend_ok else f"{C_RED}🔴 OFFLINE{C_RESET}"
            st_discord = f"{C_GREEN}🟢 ONLINE{C_RESET}" if discord_ok else f"{C_RED}🔴 OFFLINE{C_RESET}"
            st_visualizer = f"{C_GREEN}🟢 READY{C_RESET}" if visualizer_ok else f"{C_RED}🔴 OFF (Cần Backend){C_RESET}"

            SYSTEM_STATUS = (st_backend, st_frontend, st_discord, st_visualizer)
        except Exception:
            pass
        time.sleep(3.0)

# Start background status updater
threading.Thread(target=background_status_updater, daemon=True).start()

def get_status_indicators():
    return SYSTEM_STATUS

def render_main_menu(selected_idx: int):
    global IS_FIRST_RENDER
    if IS_FIRST_RENDER:
        clear_screen()
        IS_FIRST_RENDER = False
    else:
        sys.stdout.write("\033[H")
        sys.stdout.flush()

    st_backend, st_frontend, st_discord, st_visualizer = get_status_indicators()

    banner = f"{C_RED}{C_BOLD}  ██████╗██╗  ██╗██╗███████╗  █████╗ \033[K\n ██╔════╝██║  ██║██║██╔════╝ ██╔══██╗\033[K\n ██║     ███████║██║███████╗ ███████║\033[K\n ██║     ██╔══██║██║╚════██║ ██╔══██║\033[K\n ╚██████╗██║  ██║██║███████║ ██║  ██║\033[K\n  ╚═════╝╚═╝  ╚═╝╚═╝╚══════╝ ╚═╝  ╚═╝{C_RESET}\033[K\n{C_CYAN}── CHISA AI CONTROL CENTER CLI ──{C_RESET}\033[K"
    print(banner)
    print(f" {C_BOLD}Trạng thái dịch vụ:{C_RESET}\033[K")
    print(f"  • Backend Core RAG : {st_backend} (Port 8000)\033[K")
    print(f"  • Frontend UI      : {st_frontend} (Port 5173/5174)\033[K")
    print(f"  • Bot Discord      : {st_discord}\033[K")
    print(f"  • Visualizer       : {st_visualizer} (http://localhost:8000/visualizer)\033[K")
    print(f" {C_GRAY}─────────────────────────────────────────────────────────────{C_RESET}\033[K")
    print(f" {C_YELLOW}Điều hướng: Dùng phím [↑]/[↓] + [Enter] HOẶC nhập số (1-7){C_RESET}\n\033[K")

    options = [
        ("1", "🚀 Khởi động toàn bộ Chisa (Backend, Discord Bot, Frontend, Visualizer)"),
        ("2", "⚙️  Khởi động Backend Core RAG (Port 8000 + Docker)"),
        ("3", "🎨 Khởi động Frontend (Vite)"),
        ("4", "🤖 Khởi động Bot Discord"),
        ("5", "📊 Khởi động Visualizer (Trình duyệt http://localhost:8000/visualizer)"),
        ("6", "🛑 Kill tiến trình (Menu dừng/tắt các dịch vụ)"),
        ("7", "🚪 Exit (Thoát CLI - tự động dọn dẹp tiến trình)")
    ]

    for idx, (num, label) in enumerate(options):
        if idx == selected_idx:
            print(f"  {C_BG_RED} > [{num}] {label} {C_RESET}\033[K")
        else:
            print(f"    [{num}] {label}\033[K")

    print(f"\n {C_GRAY}─────────────────────────────────────────────────────────────{C_RESET}\033[K")
    sys.stdout.write("\033[J")
    sys.stdout.flush()

def render_kill_menu(selected_idx: int):
    global IS_FIRST_RENDER
    if IS_FIRST_RENDER:
        clear_screen()
        IS_FIRST_RENDER = False
    else:
        sys.stdout.write("\033[H")
        sys.stdout.flush()

    print(f"\n{C_RED}{C_BOLD}  🛑 MENU KILL / DỪNG TIẾN TRÌNH CHISA AI{C_RESET}\033[K")
    print(f" {C_GRAY}─────────────────────────────────────────────────────────────{C_RESET}\033[K")
    print(f" {C_YELLOW}Điều hướng: Dùng phím [↑]/[↓] + [Enter] HOẶC nhập phím (a-e / 1-5){C_RESET}\n\033[K")

    options = [
        ("a", "1", "💥 Kill toàn bộ (Backend, Frontend, Bot Discord, Ports 8000, 5173, 5174)"),
        ("b", "2", "⚙️  Kill Backend và Frontend Core"),
        ("c", "3", "🤖 Kill Bot Discord"),
        ("d", "4", "📊 Kill Visualizer (Dừng Backend 8000)"),
        ("e", "5", "↩️  Quay lại Menu chính")
    ]

    for idx, (key, num, label) in enumerate(options):
        if idx == selected_idx:
            print(f"  {C_BG_RED} > [{key}/{num}] {label} {C_RESET}\033[K")
        else:
            print(f"    [{key}/{num}] {label}\033[K")

    print(f"\n {C_GRAY}─────────────────────────────────────────────────────────────{C_RESET}\033[K")
    sys.stdout.write("\033[J")
    sys.stdout.flush()

def run_kill_sub_menu():
    global IS_FIRST_RENDER
    IS_FIRST_RENDER = True
    selected_idx = 0
    max_idx = 4

    while True:
        render_kill_menu(selected_idx)
        key = read_key()

        if key == 'UP':
            selected_idx = (selected_idx - 1) % (max_idx + 1)
            continue
        elif key == 'DOWN':
            selected_idx = (selected_idx + 1) % (max_idx + 1)
            continue
        elif key == 'ENTER':
            choice_idx = selected_idx
        elif key.lower() in ('a', '1'):
            choice_idx = 0
        elif key.lower() in ('b', '2'):
            choice_idx = 1
        elif key.lower() in ('c', '3'):
            choice_idx = 2
        elif key.lower() in ('d', '4'):
            choice_idx = 3
        elif key.lower() in ('e', '5', 'q'):
            break
        else:
            continue

        if choice_idx == 0:
            kill_all_services()
            break
        elif choice_idx == 1:
            kill_backend_frontend_core()
            break
        elif choice_idx == 2:
            kill_discord_bot()
            break
        elif choice_idx == 3:
            kill_visualizer()
            break
        elif choice_idx == 4:
            break

# ── Main Entry Point ─────────────────────────────────────────────────

def main():
    selected_idx = 0
    max_idx = 6

    while True:
        try:
            render_main_menu(selected_idx)
            key = read_key()

            if key == 'UP':
                selected_idx = (selected_idx - 1) % (max_idx + 1)
                continue
            elif key == 'DOWN':
                selected_idx = (selected_idx + 1) % (max_idx + 1)
                continue
            elif key == 'ENTER':
                choice = selected_idx + 1
            elif key in ('1', '2', '3', '4', '5', '6', '7'):
                choice = int(key)
            else:
                continue

            if choice == 1:
                launch_all()
                IS_FIRST_RENDER = True
            elif choice == 2:
                launch_backend()
                IS_FIRST_RENDER = True
            elif choice == 3:
                launch_frontend()
                IS_FIRST_RENDER = True
            elif choice == 4:
                launch_discord()
                IS_FIRST_RENDER = True
            elif choice == 5:
                launch_visualizer()
                IS_FIRST_RENDER = True
            elif choice == 6:
                run_kill_sub_menu()
                IS_FIRST_RENDER = True
            elif choice == 7:
                print(f"\n{C_YELLOW}[CLI] Đang thoát và dọn dẹp tiến trình...{C_RESET}")
                cleanup_all_spawned()
                print(f"{C_GREEN}[CLI] Cảm ơn Senpai đã sử dụng Chisa AI Control Center! Bye bye~{C_RESET}")
                sys.exit(0)

        except KeyboardInterrupt:
            print(f"\n{C_YELLOW}[CLI] Đã nhận tín hiệu dừng. Đang dọn dẹp...{C_RESET}")
            cleanup_all_spawned()
            sys.exit(0)

if __name__ == "__main__":
    main()
