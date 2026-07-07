import os
import sys
import time
import subprocess
import webbrowser
import urllib.request
import urllib.error

# Add project path to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def kill_process_on_port(port: int):
    """Find and terminate any process listening on the specified port."""
    print("[Chisa AI] Cleaning up port {} before starting...".format(port))
    if os.name == 'nt':
        try:
            cmd = "netstat -ano | findstr :{}".format(port)
            output = subprocess.check_output(cmd, shell=True).decode('utf-8')
            pids = set()
            for line in output.strip().split('\n'):
                if "LISTENING" in line:
                    parts = line.split()
                    if len(parts) >= 5:
                        pids.add(parts[-1])
            
            for pid in pids:
                print("[Chisa AI] Terminating process {} using port {}...".format(pid, port))
                subprocess.run("taskkill /F /T /PID {}".format(pid), shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except subprocess.CalledProcessError:
            # findstr returns non-zero exit code if no matches found
            pass
        except Exception as e:
            print("[Chisa AI] Error cleaning up port {}: {}".format(port, e))
    else:
        try:
            cmd = "lsof -t -i:{}".format(port)
            output = subprocess.check_output(cmd, shell=True).decode('utf-8')
            pids = output.strip().split('\n')
            for pid in pids:
                if pid:
                    print("[Chisa AI] Terminating process {} using port {}...".format(pid, port))
                    subprocess.run("kill -9 {}".format(pid), shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except subprocess.CalledProcessError:
            pass
        except Exception as e:
            print("[Chisa AI] Error cleaning up port {}: {}".format(port, e))

def check_backend_running(url: str) -> bool:
    """Check if the backend API is reachable."""
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            return response.status == 200
    except Exception:
        return False

def main():
    health_url = "http://localhost:8000/health"
    visualizer_url = "http://localhost:8000/visualizer"
    
    # Clean up port 8000 before proceeding
    kill_process_on_port(8000)
    
    print("[Chisa AI] Waiting for port to release...")
    for _ in range(15):
        if not check_backend_running(health_url):
            break
        time.sleep(0.2)
    
    print("[Chisa AI] Checking Backend API status...")
    
    is_running = check_backend_running(health_url)
    
    if is_running:
        print("[Chisa AI] Backend is already running! Opening Visualizer...")
    else:
        print("[Chisa AI] Backend is not running. Starting FastAPI server...")
        
        # Determine the uvicorn command
        cwd = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cmd = [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "localhost", "--port", "8000", "--reload"]
        
        try:
            process = subprocess.Popen(
                cmd,
                cwd=cwd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                shell=(os.name == 'nt')
            )
            print("[Chisa AI] FastAPI server started (PID: {}). Waiting 3 seconds...".format(process.pid))
            time.sleep(3.0)
        except Exception as e:
            print("[Chisa AI] Error starting uvicorn: {}".format(e))
            print("Please run manually: uvicorn app.main:app --reload")
            return

    # Open the visualizer dashboard in browser
    print("[Chisa AI] Opening web browser at: {}".format(visualizer_url))
    webbrowser.open(visualizer_url)
    
    print("\n=======================================================")
    print("       CHISA AI PIPELINE VISUALIZATION ACTIVE")
    print("=======================================================")
    print(" - Link Visualizer: {}".format(visualizer_url))
    print(" - Logo: /assets/dance_chisa.gif (cùng website Chisa)")
    print(" - Theme: đỏ–đen gradient (giống website Chisa)")
    print(" - Flex Budget breakdown: step 'Prompt Build' (context_building)")
    print(" - Web Search: node 'Web Search' (snippets, URLs, deep page)")
    print(" - Press Ctrl+C to exit this script.")
    print("=======================================================")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[Chisa AI] Stopped visualizer script. (FastAPI backend remains running).")

if __name__ == "__main__":
    main()
