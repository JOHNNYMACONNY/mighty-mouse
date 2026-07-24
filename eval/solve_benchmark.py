import os
import sys
import json
import subprocess
import shutil
from datetime import datetime
from compute_scaler import invoke_with_scaling

def run_command(cmd, cwd="."):
    if isinstance(cmd, str):
        import shlex
        cmd = shlex.split(cmd)
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
    return result.returncode, result.stdout, result.stderr

def solve_tasks(tier="tier_1", mode="single", concurrency=1):
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
            
        # 3. Invoke Antigravity agent path with Compute Scaling
        print(f"Invoking Antigravity agent with Compute Scaling (mode={mode}, concurrency={concurrency})...")
        agent_cmd = f"python3 src/mighty_mouse/orchestrator/mighty_mouse_agent.py {prompt_config} '{task_path}' --mode {mode} --concurrency {concurrency}"
        ret, out, err = invoke_with_scaling(agent_cmd, task_path, variations=3)
        
        # 4. Save execution trace/logs outside reset scope
        trace_file = os.path.join(results_dir, f"{task_file}_trace.log")
        with open(trace_file, "w") as f:
            f.write(f"STDOUT:\n{out}\n\nSTDERR:\n{err}")
            
        # 5. Continue verification
        print(f"Running verification for {task_path}...")
        subprocess.run(["python3", "src/mighty_mouse/services/verifiers/run_benchmark.py", task_path])
        
        # Standardize result location
        parsed_result = None
        if os.path.exists("logs/benchmark_results.json"):
            with open("logs/benchmark_results.json", "r") as f:
                bench_results = json.load(f)
                current_id = task_data.get('id')
                results_list = bench_results if isinstance(bench_results, list) else bench_results.get("results", [])
                for res in results_list:
                    if isinstance(res, dict) and res.get('task_id') == current_id:
                        parsed_result = res
                        break

        if not parsed_result and mode == "swarm":
            # Extract swarm JSON output from stdout
            try:
                swarm_out = json.loads(out.strip())
                verdict = swarm_out.get("review", {}).get("verdict", "REJECT")
                parsed_result = {
                    "task_id": task_data.get("id"),
                    "status": "success" if verdict == "PASS" else "failed",
                    "reason": swarm_out.get("review", {}).get("reason", "")
                }
            except Exception:
                pass

        if not parsed_result:
            parsed_result = {
                "task_id": task_data.get("id"),
                "status": "failed",
                "reason": "Verification missing"
            }

        all_results.append(parsed_result)

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
    parser.add_argument("--mode", choices=["single", "swarm"], default="single")
    parser.add_argument("--concurrency", type=int, choices=[1, 2], default=1)
    parser.add_argument("--parallel", action="store_true")
    args = parser.parse_args()

    if args.parallel:
        print(f"[*] Switching to Parallel Execution Mode (Tier: {args.tier})...")
        import run_parallel
        run_parallel.main(args.tier)
    else:
        solve_tasks(args.tier, mode=args.mode, concurrency=args.concurrency)
