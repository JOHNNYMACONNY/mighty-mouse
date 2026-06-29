import argparse
import json
import os
import sys
import time
import subprocess
import shutil
import yaml
from datetime import datetime

# Add src/mighty_mouse/orchestrator and eval to path
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.join(_REPO_ROOT, "src", "mighty_mouse", "orchestrator"))
sys.path.append(os.path.join(_REPO_ROOT, "eval"))

def run_hybrid(config_path, task_path, workspace, trials=2):
    root_dir = os.getcwd()
    task_id = os.path.basename(task_path).replace(".json", "")
    
    def log(msg):
        print(f"[hybrid] {msg}", file=sys.stderr)

    # 1. Run Lean (Single Pass - using standard multi-round logic if trials > 1)
    # We disable cleanup so we can archive artifacts if it fails
    log(f"[*] Running LEAN pass for {task_id} with {trials} trials...")
    from run_parallel import run_task
    
    start_wall = time.time()
    # Ensure workspace exists and is clean before Lean
    if os.path.exists(workspace):
        shutil.rmtree(workspace)
    os.makedirs(workspace, exist_ok=True)
    
    lean_res = run_task(task_path, variant="lean", config_path=config_path, trials=trials, cleanup=False)
    
    lean_status = lean_res.get("status")
    lean_category = lean_res.get("category")
    lean_latency = lean_res.get("latency_seconds", 0)
    
    result = {
        "task_id": task_id,
        "mode": "hybrid",
        "final_status": lean_status,
        "final_category": lean_category,
        "outcome": "LEAN_SUCCESS" if lean_status == "success" else "FINAL_FAIL",
        "recovered": False,
        "fallback_triggered": False,
        "lean_attempt": {
            "status": lean_status,
            "category": lean_category,
            "latency": lean_latency
        },
        "total_wall_clock": round(time.time() - start_wall, 2)
    }

    # 2. Check Fallback Trigger
    # Do not trigger fallback for: SCOPE, PARSER, ADHERENCE, VERIFICATION
    if lean_status == "fail" and lean_category in ["LOGIC", "TIMEOUT"]:
        log(f"[!] Lean failed with {lean_category}. Triggering DECOMPOSED fallback...")
        result["fallback_triggered"] = True
        result["fallback_reason"] = lean_category
        
        # Archive Lean Artifacts
        archive_dir = os.path.join(root_dir, "logs/hybrid", task_id, "lean")
        if os.path.exists(archive_dir):
            shutil.rmtree(archive_dir)
        os.makedirs(os.path.dirname(archive_dir), exist_ok=True)
        shutil.copytree(workspace, archive_dir)
        log(f"[*] Archived Lean artifacts to {archive_dir}")
        
        # Nuke Sandbox using shutil.rmtree
        log(f"[*] Nuking workspace {workspace} for clean Decomposed start...")
        shutil.rmtree(workspace)
        
        # Verify Cleanup
        if os.path.exists(workspace):
            log("[!] ERROR: Workspace still exists after shutil.rmtree!")
            # Force cleanup again if somehow it failed
            shutil.rmtree(workspace, ignore_errors=True)
            
        os.makedirs(workspace, exist_ok=True)
        # Final verification that it's empty
        if os.listdir(workspace):
            log("[!] ERROR: Workspace is not empty after recreate!")
            
        # Run Decomposed (V2)
        decomposed_script = os.path.join(root_dir, "eval/run_decomposed_v2.py")
        env = dict(os.environ)
        env["PYTHONPATH"] = f"{root_dir}:{os.path.join(root_dir, 'src/mighty_mouse/orchestrator')}:{os.path.join(root_dir, 'eval')}"
        
        start_df = time.time()
        df_res = {}
        try:
            # We run Decomposed V2 as a subprocess
            cmd = [sys.executable, decomposed_script, "--config", config_path, "--task", task_path, "--workspace", workspace]
            df_proc = subprocess.run(cmd, capture_output=True, text=True, env=env)
            
            # Try to parse JSON from stdout (it might have logs before the JSON)
            stdout = df_proc.stdout
            if "{" in stdout and "}" in stdout:
                json_str = stdout[stdout.find("{"):stdout.rfind("}")+1]
                df_res = json.loads(json_str)
            else:
                log(f"[!] Decomposed fallback produced no JSON. Stdout: {stdout}")
                df_res = {"status": "fail", "category": "PARSER", "reason": "No JSON output"}
                
        except Exception as e:
            df_res = {"status": "fail", "category": "PARSER", "reason": str(e)}
            log(f"[!] Decomposed fallback crashed: {e}")

        df_status = df_res.get("status", "fail")
        df_category = df_res.get("category", "UNKNOWN")
        df_latency = round(time.time() - start_df, 2)
        
        result["fallback_attempt"] = {
            "runner": "decomposed_v2",
            "status": df_status,
            "category": df_category,
            "latency": df_latency,
            "subtask_count": df_res.get("telemetry", {}).get("subtask_count", 0),
            "avg_subtask_latency": df_res.get("telemetry", {}).get("avg_subtask_latency", 0),
            "parser_status": df_res.get("telemetry", {}).get("parser_status", "UNKNOWN"),
            "verification_status": df_res.get("telemetry", {}).get("verification_status", "UNKNOWN")
        }
        
        if df_status == "success":
            result["final_status"] = "success"
            result["final_category"] = "SUCCESS" # Strictly keep SUCCESS as category
            result["recovered"] = True
            result["outcome"] = "RECOVERED"
        else:
            result["final_status"] = "fail"
            result["final_category"] = df_category
            result["outcome"] = "FINAL_FAIL"
            
    else:
        # No fallback triggered
        if lean_status != "success":
            result["outcome"] = "NO_TRIGGER_FAIL"
        else:
            result["outcome"] = "LEAN_SUCCESS"
            result["final_category"] = "SUCCESS"

    # Capture files touched (placeholder for now, can be extracted from Decomposed telemetry if available)
    result["files_touched"] = lean_res.get("telemetry", {}).get("files_touched", [])
    if result.get("fallback_attempt") and "files_touched" in df_res.get("telemetry", {}):
        result["files_touched"] = list(set(result["files_touched"] + df_res["telemetry"]["files_touched"]))

    result["safety_taxonomy_counts"] = {
        "logic": 1 if lean_category == "LOGIC" else 0,
        "timeout": 1 if lean_category == "TIMEOUT" else 0
    }

    result["total_wall_clock"] = round(time.time() - start_wall, 2)
    
    # Final cleanup of workspace if successful or done
    if os.path.exists(workspace):
        shutil.rmtree(workspace, ignore_errors=True)
        
    return result

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config")
    parser.add_argument("--task")
    parser.add_argument("--workspace")
    parser.add_argument("--trials", type=int, default=2)
    args = parser.parse_args()
    
    res = run_hybrid(args.config, args.task, args.workspace, trials=args.trials)
    
    # Save result to the evaluation-specific report file
    os.makedirs("eval/results", exist_ok=True)
    report_path = "eval/results/hybrid_scout_report.json"
    
    # Update existing report if it exists
    all_results = []
    if os.path.exists(report_path):
        try:
            with open(report_path, "r") as f:
                report_data = json.load(f)
                all_results = report_data.get("results", [])
        except:
            pass
            
    # Upsert result
    all_results = [r for r in all_results if r["task_id"] != res["task_id"]]
    all_results.append(res)
    
    with open(report_path, "w") as f:
        json.dump({"results": all_results}, f, indent=2)
        
    print(json.dumps(res))
