import os
import sys
import json
import subprocess
import shutil
from datetime import datetime

def run_command(cmd, cwd="."):
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=cwd)
    return result.returncode, result.stdout, result.stderr

def solve_tasks(tier="tier_1"):
    config_path = "eval/evaluation_config.json"
    results_dir = "eval/results"
    prompt_config = "configs/mighty_mouse_v1.yaml"
    
    if not os.path.exists(config_path):
        print(f"Error: Config path {config_path} not found.")
        return

    with open(config_path, 'r') as f:
        config = json.load(f)
        
    tasks_to_run = config["tiers"].get(tier, [])
    if tasks_to_run == "all":
        tasks_to_run = [f for f in os.listdir("tasks/benchmark") if f.endswith(".json")]

    os.makedirs(results_dir, exist_ok=True)
    
    all_results = []

    for task_file in tasks_to_run:
        task_path = os.path.join("tasks/benchmark", task_file)
        if not os.path.exists(task_path):
            print(f"Warning: Task file {task_file} not found.")
            continue

        print(f"--- Processing Task: {task_file} ---")
        
        # 1. Pre-task reset
        print("Resetting workspace...")
        subprocess.run(["bash", "eval/reset_workspace.sh"])
        
        # 2. Load task JSON
        with open(task_path, 'r') as f:
            task_data = json.load(f)
            
        # 3. Invoke Antigravity agent path
        print("Invoking Antigravity agent...")
        agent_cmd = f"python3 src/orchestrator/mighty_mouse_agent.py {prompt_config} '{task_path}'"
        ret, out, err = run_command(agent_cmd)
        
        # 4. Save execution trace/logs outside reset scope
        trace_file = os.path.join(results_dir, f"{task_file}_trace.log")
        with open(trace_file, "w") as f:
            f.write(f"STDOUT:\n{out}\n\nSTDERR:\n{err}")
            
        # 5. Continue verification
        print(f"Running verification for {task_path}...")
        subprocess.run(["python3", "eval/run_benchmark.py", task_path])
        
        # Standardize result location
        if os.path.exists("logs/benchmark_results.json"):
            with open("logs/benchmark_results.json", "r") as f:
                bench_results = json.load(f)
                current_id = task_data.get('id')
                results_list = bench_results if isinstance(bench_results, list) else bench_results.get("results", [])
                for res in results_list:
                    if isinstance(res, dict) and res.get('task_id') == current_id:
                        all_results.append(res)
                        break

    # Final consolidate results
    success_count = len([r for r in all_results if r["status"] == "success"])
    final_payload = {
        "summary": {
            "success_rate": f"{success_count}/{len(all_results)}",
            "timestamp": datetime.now().isoformat(),
            "mode": "sequential"
        },
        "results": all_results
    }
    final_output = os.path.join(results_dir, "benchmark_results.json")
    with open(final_output, "w") as f:
        json.dump(final_payload, f, indent=2)
        
    print(f"Benchmark iteration complete. Results saved to {final_output}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--tier", default="tier_1")
    parser.add_argument("--parallel", action="store_true")
    args = parser.parse_args()

    if args.parallel:
        print(f"[*] Switching to Parallel Execution Mode (Tier: {args.tier})...")
        import run_parallel
        run_parallel.main(args.tier)
    else:
        solve_tasks(args.tier)
