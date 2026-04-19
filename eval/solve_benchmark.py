import os
import sys
import json
import subprocess
import shutil

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
        print("Running verification...")
        subprocess.run(["python3", "eval/run_benchmark.py"])
        
        # Standardize result location
        if os.path.exists("logs/benchmark_results.json"):
            with open("logs/benchmark_results.json", "r") as f:
                bench_results = json.load(f)
                current_id = task_data.get('id')
                for res in bench_results:
                    if res.get('task_id') == current_id:
                        all_results.append(res)
                        break

    # Final consolidate results
    final_output = os.path.join(results_dir, "benchmark_results.json")
    with open(final_output, "w") as f:
        json.dump(all_results, f, indent=2)
        
    print(f"Benchmark iteration complete. Results saved to {final_output}")

if __name__ == "__main__":
    tier = sys.argv[1] if len(sys.argv) > 1 else "tier_1"
    solve_tasks(tier)
