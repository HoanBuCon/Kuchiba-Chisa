import os
import sys
import time
import psutil
import subprocess
import requests

def cleanup_processes():
    """
    Kills any existing Celery or Uvicorn processes to ensure a clean slate 
    and release bound ports (like 8000).
    """
    print("[Cleanup] Scanning for stuck Celery/Uvicorn processes...")
    killed_count = 0
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            cmdline = proc.info.get('cmdline') or []
            cmd_str = " ".join(cmdline).lower()
            
            # Match uvicorn or celery processes
            if 'uvicorn' in cmd_str or 'celery' in cmd_str:
                # Do not kill the test script itself
                if 'test_production_flow.py' not in cmd_str:
                    print(f"  -> Killing stuck process: PID {proc.info['pid']} | {cmd_str[:60]}...")
                    proc.kill()
                    killed_count += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
            
    if killed_count > 0:
        print(f"[Cleanup] Killed {killed_count} processes. Waiting 3s for ports to clear...")
        time.sleep(3)
    else:
        print("[Cleanup] System clean.")

def wait_for_fastapi(url="http://127.0.0.1:8000/openapi.json", timeout=30):
    print(f"[Wait] Waiting for FastAPI to be ready at {url}...")
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            res = requests.get(url, timeout=2)
            if res.status_code == 200:
                print(f"[Wait] FastAPI is ready! (Took {time.time() - start_time:.1f}s)")
                return True
        except requests.ConnectionError:
            pass
        time.sleep(1)
    print("[Wait] ERROR: FastAPI failed to start within timeout.")
    return False

def run_production_flow():
    celery_proc = None
    uvicorn_proc = None
    
    # 1. Ensure clean slate
    cleanup_processes()
    
    try:
        # 2. Start Celery Worker
        # Note: On Windows, Celery requires a pool like gevent, eventlet, or solo to work correctly.
        print("[Start] Launching Celery Worker (background)...")
        celery_cmd = [sys.executable, "-m", "celery", "-A", "app.infrastructure.tasks.celery_app", "worker", "--loglevel=info", "-P", "solo"]
        celery_proc = subprocess.Popen(celery_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        # 3. Start FastAPI Server
        print("[Start] Launching FastAPI Server (background)...")
        uvicorn_cmd = [sys.executable, "-m", "uvicorn", "app.main:app", "--port", "8000"]
        uvicorn_proc = subprocess.Popen(uvicorn_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        # 4. Wait for API Health
        if not wait_for_fastapi():
            raise Exception("FastAPI did not start properly. Aborting test.")
            
        # 5. Trigger Sync API
        print("[Test] Triggering Wiki Sync via API (Limit=1)...")
        res = requests.post("http://127.0.0.1:8000/api/v1/admin/ingestion/sync", params={"limit": 1})
        if res.status_code == 200:
            print("[Test] Sync trigger SUCCESS:", res.json())
        else:
            raise Exception(f"Failed to trigger sync: {res.status_code} {res.text}")
            
        # 6. Wait for pipeline to process (Celery working in background)
        print("[Test] Waiting 15 seconds for Celery to download and process the Wiki page...")
        for i in range(15, 0, -1):
            print(f"  ... {i}s remaining", end="\r")
            time.sleep(1)
        print("  ... Done waiting.       ")
        
        # 7. Run Evaluation Script to verify Vectors reached Qdrant
        print("[Test] Running Retrieval Evaluation Script (Recall@5)...")
        eval_cmd = [sys.executable, "-m", "scripts.evaluate_retrieval", "--dataset", "data/golden_dataset.json"]
        
        # We need to set PYTHONPATH to the current directory so Python can find 'app'
        env = os.environ.copy()
        env["PYTHONPATH"] = os.path.abspath(".")
        
        eval_proc = subprocess.run(eval_cmd, capture_output=True, text=True, env=env)
        
        print("\n=== Evaluation Results ===")
        print(eval_proc.stdout)
        
        if eval_proc.returncode == 0:
            print("✅ PRODUCTION FLOW TEST PASSED!")
        else:
            print("❌ PRODUCTION FLOW TEST FAILED!")
            print(eval_proc.stderr)
            
    finally:
        # 8. Teardown
        print("\n[Teardown] Shutting down background processes...")
        if celery_proc:
            celery_proc.terminate()
        if uvicorn_proc:
            uvicorn_proc.terminate()
            
        # Hard cleanup just in case terminate() fails
        cleanup_processes()
        print("[Teardown] Complete.")

if __name__ == "__main__":
    run_production_flow()
