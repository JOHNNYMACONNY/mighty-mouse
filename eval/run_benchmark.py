import subprocess
import os
import json
import pandas as pd
from datetime import datetime

def get_modified_files():
    """Returns a list of files modified or added in the workspace."""
    result = subprocess.run(['git', 'status', '--porcelain'], capture_output=True, text=True)
    modified = []
    for line in result.stdout.splitlines():
        if line.strip():
            # git status --porcelain output: XY path
            # We take everything from index 3 onwards
            path = line[3:].strip()
            modified.append(path)
    return modified

def verify_task(task_config):
    task_id = task_config['id']
    test_script = task_config['test_script']
    expected_files = task_config['expected_files']
    
    # Check Workflow Adherence (Mighty Mouse Core)
    adherence_check = subprocess.run(['python3', 'src/orchestrator/enforce_workflow.py', 'CHECKLIST.md'], capture_output=True, text=True)
    adherence_passed = (adherence_check.returncode == 0)
    adherence_logs = adherence_check.stdout + adherence_check.stderr

    # Check for Unnecessary Edits (Strict File Scope)
    modified_files = get_modified_files()
    # Normalize paths for comparison (optional but safe)
    unexpected_files = [f for f in modified_files if f not in expected_files and f != 'CHECKLIST.md']
    
    scope_passed = len(unexpected_files) == 0
    scope_msg = f"Unexpected files modified: {unexpected_files}" if not scope_passed else "Scope verified."

    # Check if expected files exist
    files_exist = all(os.path.exists(f) for f in expected_files)
    
    if not files_exist:
        return {
            "task_id": task_id,
            "status": "fail",
            "reason": "Missing expected files",
            "timestamp": datetime.now().isoformat()
        }

    # Run the test
    with open('test_runner.py', 'w') as f:
        f.write(test_script)
        
    try:
        # Run with absolute path to ensure no environment confusion
        result = subprocess.run(['python3', 'test_runner.py'], capture_output=True, text=True, timeout=10)
        passed = (result.returncode == 0)
        logs = result.stdout + result.stderr
    except Exception as e:
        passed = False
        logs = str(e)
        
    # Cleanup
    if os.path.exists('test_runner.py'):
        os.remove('test_runner.py')
        
    status = "success" if (passed and adherence_passed and scope_passed) else "fail"
    
    return {
        "task_id": task_id,
        "status": status,
        "adherence": "PASS" if adherence_passed else "FAIL",
        "scope": "PASS" if scope_passed else "FAIL",
        "reason": scope_msg if not scope_passed else ("Tests failed" if not passed else "Workflow failed"),
        "adherence_logs": adherence_logs,
        "test_logs": logs,
        "timestamp": datetime.now().isoformat()
    }

def main():
    benchmark_dir = "tasks/benchmark"
    logs_dir = "logs"
    os.makedirs(logs_dir, exist_ok=True)
    
    results = []
    
    for filename in sorted(os.listdir(benchmark_dir)):
        if filename.endswith(".json") and not filename.startswith("."):
            with open(os.path.join(benchmark_dir, filename), 'r') as f:
                task_config = json.load(f)
                res = verify_task(task_config)
                results.append(res)
                
    # Save results
    with open(os.path.join(logs_dir, "benchmark_results.json"), 'w') as f:
        json.dump(results, f, indent=2)
        
    print(f"Verified {len(results)} tasks. Results logged to {logs_dir}/benchmark_results.json")

if __name__ == "__main__":
    main()
