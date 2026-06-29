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
    s_pass, s_msg, s_telemetry = check_scope(task_config)
    t_pass, t_log = run_task_tests(test_script)
    status = "success" if (a_pass and s_pass and t_pass) else "fail"
    update_checkpoint(task_id)
    
    res = {
        "task_id": task_id, "status": status, "adherence": "PASS" if a_pass else "FAIL",
        "scope": "PASS" if s_pass else "FAIL", "reason": s_msg if not s_pass else ("Tests failed" if not t_pass else ("Adherence failed" if not a_pass else "All checks passed")),
        "adherence_logs": a_log, "test_logs": t_log, "timestamp": datetime.now().isoformat()
    }
    # Integrate Scope Telemetry
    res.update(s_telemetry)
    return res

def main():
    if len(sys.argv) > 1:
        task_path = sys.argv[1]
        with open(task_path, 'r') as f:
            task_config = json.load(f)
            res = verify_task(task_config)
            history_path = "logs/benchmark_results.json"
            data = _get_json_data(history_path, {"results": []})
            
            # Extract results list
            if isinstance(data, list):
                history_list = data
            else:
                history_list = data.get("results", [])

            # Update history: Preserve telemetry keys if they exist
            existing_record = next((h for h in history_list if h['task_id'] == res['task_id']), {})
            history_list = [h for h in history_list if h['task_id'] != res['task_id']]
            
            # Merge: 'res' (new verification) takes precedence, but 'existing_record' preserves telemetry
            merged_res = {**existing_record, **res}
            history_list.append(merged_res)
            
            # Save back in dict format
            if isinstance(data, dict):
                data["results"] = history_list
                # Update summary if present
                if "summary" in data:
                    success_count = len([r for r in history_list if r["status"] == "success"])
                    data["summary"]["success_rate"] = f"{success_count}/{len(history_list)}"
                    data["summary"]["timestamp"] = datetime.now().isoformat()
                    data["summary"]["updated_by"] = "run_benchmark"
                _save_json_data(history_path, data)
            else:
                _save_json_data(history_path, history_list)
            print(json.dumps(res, indent=2))
            print(f"Task {res['task_id']} {res['status']}: {res['reason']}")


if __name__ == "__main__": main()
