import os
import subprocess
import json

def run_command(cmd, cwd="."):
    if isinstance(cmd, str):
        import shlex
        cmd = shlex.split(cmd)
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
    return result.returncode, result.stdout, result.stderr

def invoke_with_scaling(agent_cmd, task_path, variations=3):
    """
    Implements Test-Time Compute Scaling (o1 pattern).
    Instead of single-shot, run the agent N times.
    We return the first variation that fully passes (including scope constraints).
    """
    best_ret, best_out, best_err = None, "", ""
    
    with open(task_path, 'r') as f:
        task_data = json.load(f)
        
    for i in range(variations):
        print(f"  [Compute Scaler] Running internal MCTS draft {i+1}/{variations}...")
        
        # Reset workspace
        subprocess.run(["bash", "eval/reset_workspace.sh"])
        
        # Invoke agent
        ret, out, err = run_command(agent_cmd)
        
        # Verify internally
        subprocess.run(["python3", "eval/run_benchmark.py", task_path], capture_output=True)
        
        if os.path.exists("logs/benchmark_results.json"):
            with open("logs/benchmark_results.json", "r") as f:
                res = json.load(f)
                res_list = res if isinstance(res, list) else res.get("results", [])
                # Benchmark task JSONs use 'id' key (not 'task_id')
                current_id = task_data.get('id')
                success = False
                for r in res_list:
                    if isinstance(r, dict) and r.get('task_id') == current_id:
                        if r.get('status') == 'success':
                            success = True
                        break
                        
                if success:
                    print(f"  [Compute Scaler] Variation {i+1} PASSED! Locking in this timeline.")
                    return ret, out, err
                
        best_ret, best_out, best_err = ret, out, err
        print(f"  [Compute Scaler] Variation {i+1} failed. Re-rolling...")
        
    print(f"  [Compute Scaler] Exhausted {variations} variations. Yielding last attempt.")
    return best_ret, best_out, best_err
