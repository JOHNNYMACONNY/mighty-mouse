import os
import sys
import json
import subprocess
import concurrent.futures
import shutil
from datetime import datetime

TASK_DIR = "tasks/benchmark"
LOG_PATH = "logs/benchmark_results.json"
MAX_WORKERS = 8
CONFIG = "configs/mighty_mouse_v1.yaml"

def run_task(task_path):
    task_id = os.path.basename(task_path).replace(".json", "")
    task_abs = os.path.abspath(task_path)
    root_dir = os.getcwd()
    workspace = os.path.join(root_dir, f"workspaces/{task_id}")
    
    config_abs = os.path.join(root_dir, CONFIG)
    agent_abs = os.path.join(root_dir, "src/orchestrator/mighty_mouse_agent.py")
    verify_abs = os.path.join(root_dir, "eval/run_benchmark.py")
    
    if not os.path.exists(workspace):
        os.makedirs(workspace, exist_ok=True)
    
    success = False
    feedback = "No feedback"
    
    try:
        # Multi-directory PYTHONPATH for module resolution
        env = dict(os.environ)
        env["PYTHONPATH"] = f"{root_dir}:{os.path.join(root_dir, 'src/orchestrator')}:{os.path.join(root_dir, 'eval')}"
        
        for r in range(1, 3):
            cmd = [sys.executable, agent_abs, config_abs, task_abs]
            if r > 1: cmd.extend(["--feedback", feedback])
            
            # Agent Run
            subprocess.run(cmd, capture_output=True, text=True, cwd=workspace, env=env, timeout=60)
            
            # Verify Run
            ver_res = subprocess.run([sys.executable, verify_abs, task_abs], capture_output=True, text=True, cwd=workspace, env=env)
            
            if "success" in ver_res.stdout.lower():
                success = True
                break
            else:
                feedback = ver_res.stdout if ver_res.stdout else "Verification failed"
        
        shutil.rmtree(workspace, ignore_errors=True)
        return {"task_id": task_id, "status": "success" if success else "fail", "reason": feedback if not success else None, "timestamp": datetime.now().isoformat()}
    except Exception as e:
        shutil.rmtree(workspace, ignore_errors=True)
        return {"task_id": task_id, "status": "fail", "reason": str(e), "timestamp": datetime.now().isoformat()}

def main():
    if not os.path.exists("logs"): os.makedirs("logs")
    if not os.path.exists("workspaces"): os.makedirs("workspaces")
    
    tasks = [os.path.join(TASK_DIR, f) for f in os.listdir(TASK_DIR) if f.endswith(".json")]
    tasks.sort()
    
    print(f"[*] Dispatching {len(tasks)} tasks...")
    results = []
    with concurrent.futures.ProcessPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(run_task, t): t for t in tasks}
        for future in concurrent.futures.as_completed(futures):
            results.append(future.result())

    with open(LOG_PATH, "w") as f:
        json.dump(results, f, indent=2)
    
    success_count = len([r for r in results if r["status"] == "success"])
    print(f"[*] Done. Success: {success_count}/{len(results)}")

if __name__ == "__main__":
    main()
