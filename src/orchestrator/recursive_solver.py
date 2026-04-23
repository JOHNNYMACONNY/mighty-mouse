import subprocess
import sys
import os
import json

def run_step(command):
    print(f"Running: {' '.join(command)}")
    result = subprocess.run(command, capture_output=True, text=True)
    return result.returncode == 0, result.stdout, result.stderr

def solve_recursive(config, task, workspace, max_retries=3):
    feedback = None
    for i in range(max_retries + 1):
        print(f"\n--- ATTEMPT {i+1} ---")
        
        # 1. Run Agent
        cmd = [sys.executable, "src/orchestrator/mighty_mouse_agent.py", config, task, "--workspace", workspace]
        if feedback:
            cmd += ["--feedback", feedback]
        
        success, out, err = run_step(cmd)
        if not success:
            feedback = f"Agent crashed: {err}"
            continue

        # 2. Verify Workflow
        checklist_path = os.path.join(workspace, "CHECKLIST.md")
        cmd = [sys.executable, "src/orchestrator/enforce_workflow.py", checklist_path]
        success, out, err = run_step(cmd)
        if not success:
            feedback = f"Workflow Violation: {out}"
            continue

        # 3. Verify Functionality (Benchmark)
        cmd = [sys.executable, "eval/run_benchmark.py", task]
        # We need to run this inside the workspace environment
        # but for simplicity in this script we assume run_benchmark handles it
        success, out, err = run_step(cmd)
        if success:
            print("SUCCESS: Task completed and verified.")
            return True
        else:
            feedback = f"Verification Failed: {out}"
            continue

    print("FAILURE: Max retries exceeded.")
    return False

if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: python3 recursive_solver.py <config> <task> <workspace>")
        sys.exit(1)
    
    success = solve_recursive(sys.argv[1], sys.argv[2], sys.argv[3])
    sys.exit(0 if success else 1)
