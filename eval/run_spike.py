# DEPRECATED
import os
import json
import subprocess
import sys
import time
from datetime import datetime

# Subset of tasks
TASKS = [
    "tasks/benchmark/task_001_legacy_registry_ratelimiter.json",
    "tasks/benchmark/task_008_database_link_enricher.json",
    "tasks/benchmark/task_015_async_service_circuitbreaker.json"
]

VARIANTS = [
    {"name": "Baseline", "config": "configs/mighty_mouse_v1.yaml", "type": "standard"},
    {"name": "Lean Protocol", "config": "configs/mighty_mouse_lean.yaml", "type": "standard"},
    {"name": "Decomposition-First", "config": "configs/mighty_mouse_v1.yaml", "type": "decomposed"},
    {"name": "Early-Abort Fallback", "config": "configs/mighty_mouse_abort.yaml", "type": "standard"}
]

RESULTS_LOG = "logs/spike_results.jsonl"

def run_standard(config, task_path, workspace):
    agent_script = os.path.abspath("src/mighty_mouse/orchestrator/mighty_mouse_agent.py")
    config_abs = os.path.abspath(config)
    task_abs = os.path.abspath(task_path)
    workspace_abs = os.path.abspath(workspace)
    
    env = dict(os.environ)
    env["PYTHONPATH"] = f"{os.getcwd()}:{os.path.join(os.getcwd(), 'src/mighty_mouse/orchestrator')}:{os.path.join(os.getcwd(), 'eval')}"
    
    start_time = time.time()
    try:
        res = subprocess.run(
            [sys.executable, agent_script, config_abs, task_abs, "--workspace", workspace_abs],
            capture_output=True, text=True, env=env, timeout=300
        )
        latency = time.time() - start_time
        stdout = res.stdout
        stderr = res.stderr
        timeout_flag = False
    except subprocess.TimeoutExpired:
        latency = 300
        stdout = "TIMEOUT"
        stderr = ""
        timeout_flag = True

    # Verification
    verify_script_abs = os.path.abspath("eval/run_benchmark.py")
    sandbox_wrapper_abs = os.path.abspath("eval/sandbox_wrapper.py")
    task_path_abs = os.path.abspath(task_path)
    
    ver_res = subprocess.run(
        [sys.executable, sandbox_wrapper_abs, verify_script_abs, task_path_abs],
        capture_output=True, text=True, cwd=workspace_abs, env=env
    )
    
    success = '"status": "success"' in ver_res.stdout
    
    # Check for early abort tag
    controlled_abort = "<ABORT>" in stdout
    
    # Files touched (read from last_agent_run.json)
    meta_path = os.path.join(workspace, "logs/last_agent_run.json")
    files_touched = []
    if os.path.exists(meta_path):
        try:
            with open(meta_path, "r") as f:
                meta = json.load(f)
                files_touched = meta.get("written_files", [])
        except: pass

    return {
        "status": "success" if success else "fail",
        "category": "TIMEOUT" if (timeout_flag or controlled_abort) else ("LOGIC" if not success else "SUCCESS"),
        "timeout_occurred": timeout_flag,
        "controlled_abort": controlled_abort,
        "wall_clock_time": round(latency, 2),
        "files_touched": files_touched,
        "verification_status": "Passed" if success else "Failed",
        "raw_stdout": stdout
    }

def main():
    if not os.path.exists("logs"): os.makedirs("logs")
    if os.path.exists(RESULTS_LOG): os.remove(RESULTS_LOG)
    
    print(f"[*] Starting Efficiency/Decomposition Mini-Spike...")
    
    all_results = []
    
    for variant in VARIANTS:
        print(f"\n[Variant: {variant['name']}]")
        for task_path in TASKS:
            task_id = os.path.basename(task_path).replace(".json", "")
            workspace = os.path.join(os.getcwd(), f"workspaces/spike_{variant['name'].replace(' ', '_')}_{task_id}")
            if not os.path.exists(workspace): os.makedirs(workspace)
            
            print(f"  - Running {task_id}...")
            
            if variant['type'] == "standard":
                res = run_standard(variant['config'], task_path, workspace)
            else:
                # Call run_decomposed.py
                run_dec_abs = os.path.abspath("eval/run_decomposed.py")
                config_abs = os.path.abspath(variant['config'])
                task_abs = os.path.abspath(task_path)
                workspace_abs = os.path.abspath(workspace)
                
                env = dict(os.environ)
                env["PYTHONPATH"] = f"{os.getcwd()}:{os.path.join(os.getcwd(), 'src/mighty_mouse/orchestrator')}:{os.path.join(os.getcwd(), 'eval')}"
                try:
                    dec_res = subprocess.run(
                        [sys.executable, run_dec_abs, "--config", config_abs, "--task", task_abs, "--workspace", workspace_abs],
                        capture_output=True, text=True, env=env
                    )
                    try:
                        res = json.loads(dec_res.stdout)
                        res["timeout_occurred"] = False
                        res["controlled_abort"] = False
                        res["wall_clock_time"] = res.get("latency_seconds", 0)
                        res["raw_stdout"] = dec_res.stdout
                        res["raw_stderr"] = dec_res.stderr
                    except json.JSONDecodeError as e:
                        res = {
                            "status": "fail", 
                            "category": "PARSER", 
                            "reason": f"JSON Decode Error: {str(e)}\nSTDOUT: {dec_res.stdout[:500]}",
                            "wall_clock_time": 0,
                            "raw_stdout": dec_res.stdout,
                            "raw_stderr": dec_res.stderr
                        }

            res["variant"] = variant["name"]
            res["task_id"] = task_id
            res["timestamp"] = datetime.now().isoformat()
            
            # Replay Gate logic
            if task_id == "task_001_legacy_registry_ratelimiter":
                res["replay_gate_result"] = "PASS" if res["status"] == "success" else "FAIL"
            else:
                res["replay_gate_result"] = "N/A"

            all_results.append(res)
            with open(RESULTS_LOG, "a") as f:
                f.write(json.dumps(res) + "\n")
            
            time.sleep(2) # Cooldown

    print(f"\n[*] Spike Complete. Results saved to {RESULTS_LOG}")

if __name__ == "__main__":
    main()
