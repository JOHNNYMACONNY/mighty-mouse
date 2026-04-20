import subprocess
import os
import json
import sys
from datetime import datetime

def get_modified_files():
    result = subprocess.run(['git', 'status', '--porcelain'], capture_output=True, text=True)
    modified = []
    for line in result.stdout.splitlines():
        if line.strip():
            path = line[3:].strip()
            modified.append(path)
    return modified

def verify_task(task_config):
    task_id = task_config['id']
    test_script = task_config['test_script']
    expected_files = task_config['expected_files']
    
    adherence_check = subprocess.run(['python3', 'src/orchestrator/enforce_workflow.py', 'CHECKLIST.md'], capture_output=True, text=True)
    adherence_passed = (adherence_check.returncode == 0)
    adherence_logs = adherence_check.stdout + adherence_check.stderr

    modified_files = get_modified_files()
    ignored_prefixes = ['.gsd/', 'src/orchestrator/', 'eval/', '.DS_Store', 'logs/', 'autoresearch-results', 'baseline_run.log', 'configs/']
    
    unexpected_files = [
        f for f in modified_files 
        if f not in expected_files 
        and f != 'CHECKLIST.md'
        and not any(f.startswith(prefix) for prefix in ignored_prefixes)
        and not os.path.basename(f).startswith('._')
        and not f.endswith('.log')
        and not f.endswith('.tsv')
    ]
    
    scope_passed = len(unexpected_files) == 0
    scope_msg = f"Unexpected files modified: {unexpected_files}" if not scope_passed else "Scope verified."

    files_exist = all(os.path.exists(f) for f in expected_files)
    if not files_exist:
        return {"task_id": task_id, "status": "fail", "reason": f"Missing expected files: {expected_files}", "timestamp": datetime.now().isoformat()}

    with open('test_runner.py', 'w') as f: f.write(test_script)
    try:
        result = subprocess.run(['python3', 'test_runner.py'], capture_output=True, text=True, timeout=10)
        passed = (result.returncode == 0)
        logs = result.stdout + result.stderr
    except Exception as e:
        passed = False
        logs = str(e)
    if os.path.exists('test_runner.py'): os.remove('test_runner.py')
    
    status = "success" if (passed and adherence_passed and scope_passed) else "fail"
    return {
        "task_id": task_id, "status": status, 
        "adherence": "PASS" if adherence_passed else "FAIL",
        "scope": "PASS" if scope_passed else "FAIL",
        "reason": scope_msg if not scope_passed else ("Tests failed" if not passed else "Workflow failed"),
        "adherence_logs": adherence_logs, "test_logs": logs, "timestamp": datetime.now().isoformat()
    }

def main():
    logs_dir = "logs"
    os.makedirs(logs_dir, exist_ok=True)
    
    # Check if we are running for a single task
    if len(sys.argv) > 1:
        task_path = sys.argv[1]
        with open(task_path, 'r') as f:
            task_config = json.load(f)
            res = verify_task(task_config)
            
            # Load existing or start new
            history_path = os.path.join(logs_dir, "benchmark_results.json")
            if os.path.exists(history_path):
                with open(history_path, 'r') as f: history = json.load(f)
            else:
                history = []
            
            # Update or append
            history = [h for h in history if h['task_id'] != res['task_id']]
            history.append(res)
            
            with open(history_path, 'w') as f: json.dump(history, f, indent=2)
            print(f"Task {res['task_id']} {res['status']} verified.")
    else:
        print("Usage: run_benchmark.py <task_json_path>")

if __name__ == "__main__":
    main()
