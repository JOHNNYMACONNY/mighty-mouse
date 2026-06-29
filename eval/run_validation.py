import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime

# Absolute paths for stability
import os
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AGENT_SCRIPT = os.path.join(REPO_ROOT, "src/mighty_mouse/orchestrator/mighty_mouse_agent.py")
VERIFIER_SCRIPT = os.path.join(REPO_ROOT, "eval/run_benchmark.py")
TASK_DIR = os.path.join(REPO_ROOT, "tasks/benchmark")
CONFIG_DIR = os.path.join(REPO_ROOT, "configs")
WORKSPACE_BASE = os.path.join(REPO_ROOT, "workspaces")

TASKS = [
    "task_001_legacy_registry_ratelimiter.json",
    "task_002_stream_cache_validator.json",
    "task_003_legacy_link_circuitbreaker.json",
    "task_004_network_link_validator.json",
    "task_005_network_iterator_retry.json",
    "task_006_stream_composite_enricher.json",
    "task_007_cloud_queue_enricher.json",
    "task_008_database_link_enricher.json",
    "task_009_legacy_decorator_filter.json",
    "task_010_async_composite_enricher.json",
    "task_011_realtime_decorator_ratelimiter.json",
    "task_012_network_facade_retry.json",
    "task_013_network_node_retry.json",
    "task_014_legacy_store_retry.json",
    "task_015_async_service_circuitbreaker.json"
]

def run_trial(config_name, task_file, results_log):
    task_id = task_file.replace(".json", "")
    variant_name = "Baseline" if "v1" in config_name else "Lean"
    workspace = os.path.join(WORKSPACE_BASE, f"val_{variant_name}_{task_id}")
    config_path = os.path.join(CONFIG_DIR, config_name)
    task_path = os.path.join(TASK_DIR, task_file)
    
    print(f"[*] Running {variant_name} / {task_id}...")
    
    os.makedirs(workspace, exist_ok=True)
    
    env = os.environ.copy()
    env["PYTHONPATH"] = REPO_ROOT
    
    start_time = time.time()
    
    # 1. Run Agent
    agent_proc = subprocess.run(
        [sys.executable, AGENT_SCRIPT, config_path, task_path, "--workspace", workspace],
        capture_output=True, text=True, env=env
    )
    
    # 2. Run Verification
    ver_res = subprocess.run(
        [sys.executable, VERIFIER_SCRIPT, task_path],
        capture_output=True, text=True, env=env, cwd=workspace
    )
    
    wall_clock = time.time() - start_time
    
    # Parse results from workspace logs
    internal_results_path = os.path.join(workspace, "logs/benchmark_results.json")
    status = "fail"
    category = "LOGIC"
    reason = "Verification failed"
    
    if os.path.exists(internal_results_path):
        try:
            with open(internal_results_path, 'r') as f:
                data = json.load(f)
                res_obj = data.get("results", [{}])[0]
                status = res_obj.get("status", "fail")
                reason = res_obj.get("reason", "Unknown")
        except:
            pass

    # Simple category heuristic matching analyze_failure.py
    if status == "fail":
        low = reason.lower()
        if "timeout" in low: category = "TIMEOUT"
        elif "scope" in low or "unexp:" in low or "miss:" in low: category = "SCOPE"
        elif "parser" in low or "no file" in low: category = "PARSER"
        elif "workflow" in low or "adherence" in low: category = "ADHERENCE"
    else:
        category = "SUCCESS"

    result = {
        "variant": variant_name,
        "task_id": task_id,
        "status": status,
        "category": category,
        "wall_clock_time": round(wall_clock, 2),
        "timestamp": datetime.now().isoformat(),
        "reason": reason
    }
    
    with open(results_log, "a") as f:
        f.write(json.dumps(result) + "\n")
    
    return result

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true", help="Run 1 task only")
    args = parser.parse_args()
    
    task_subset = [TASKS[0]] if args.smoke else TASKS
    configs = ["mighty_mouse_v1.yaml", "mighty_mouse_lean.yaml"]
    
    results_baseline = os.path.join(REPO_ROOT, "logs/validation_baseline.jsonl")
    results_lean = os.path.join(REPO_ROOT, "logs/validation_lean.jsonl")
    
    # Clear logs if not smoke test
    if not args.smoke:
        if os.path.exists(results_baseline): os.remove(results_baseline)
        if os.path.exists(results_lean): os.remove(results_lean)

    print(f"[*] Starting Validation Pass. Smoke Mode: {args.smoke}")
    
    for config in configs:
        log_file = results_baseline if "v1" in config else results_lean
        for task in task_subset:
            run_trial(config, task, log_file)
            time.sleep(2) # Cooldown

    print("[*] Validation Pass Complete.")

if __name__ == "__main__":
    main()
