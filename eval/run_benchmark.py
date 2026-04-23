import os, json, sys, subprocess
from datetime import datetime
from verifiers.adherence import check_adherence
from verifiers.scope import verify as check_scope
from verifiers.tester import run_task_tests

def _get_json_data(path, default_val):
    if os.path.exists(path):
        try:
            with open(path, 'r') as f: return json.load(f)
        except: pass
    return default_val

def _save_json_data(path, data):
    if not os.path.exists("logs"): os.makedirs("logs")
    with open(path, 'w') as f: json.dump(data, f, indent=2)

def update_checkpoint(task_id):
    checkpoint_path = "logs/session_checkpoint.json"
    data = _get_json_data(checkpoint_path, {"completed_tasks": []})
    if task_id not in data["completed_tasks"]: data["completed_tasks"].append(task_id)
    try:
        git_hash = subprocess.check_output(['git', 'rev-parse', 'HEAD']).decode().strip()
        data["git_hash"] = git_hash
    except: pass
    _save_json_data(checkpoint_path, data)

def verify_task(task_config):
    task_id = task_config['id']
    test_script = task_config['test_script']
    expected_files = task_config['expected_files']
    a_pass, a_log = check_adherence()
    s_pass, s_msg = check_scope(expected_files)
    t_pass, t_log = run_task_tests(test_script)
    status = "success" if (a_pass and s_pass and t_pass) else "fail"
    update_checkpoint(task_id)
    return {
        "task_id": task_id, "status": status, "adherence": "PASS" if a_pass else "FAIL",
        "scope": "PASS" if s_pass else "FAIL", "reason": s_msg if not s_pass else ("Tests failed" if not t_pass else "Workflow failed"),
        "adherence_logs": a_log, "test_logs": t_log, "timestamp": datetime.now().isoformat()
    }

def main():
    if len(sys.argv) > 1:
        task_path = sys.argv[1]
        with open(task_path, 'r') as f:
            task_config = json.load(f)
            res = verify_task(task_config)
            history_path = "logs/benchmark_results.json"
            history = _get_json_data(history_path, [])
            history = [h for h in history if h['task_id'] != res['task_id']]
            history.append(res)
            _save_json_data(history_path, history)
            print(f"Task {res['task_id']} {res['status']} verified.")
            
            # Phase 7: Robustness & Failure Post-Mortems
            if res['status'] == 'fail':
                try:
                    from src.orchestrator.analyze_failure import analyze
                    analyze()
                except ImportError:
                    pass

if __name__ == "__main__": main()

