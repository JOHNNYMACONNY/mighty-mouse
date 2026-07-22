import os
import json
import subprocess
from eval.compute_scaler import invoke_with_scaling

def test_multi_turn_feedback_end_to_end(tmp_path):
    # Create mock task file
    task_file = os.path.join(tmp_path, "mock_task_scaling.json")
    with open(task_file, "w") as f:
        json.dump({
            "id": "scaling_test_task_01",
            "task": "Fix the division by zero in math_utils.py",
            "test_script": "pytest",
            "expected_files": ["math_utils.py"]
        }, f)

    # Mock agent command that logs args
    log_file = os.path.join(tmp_path, "agent_invocation_log.json")
    if os.path.exists(log_file):
        os.remove(log_file)

    agent_cmd = f"python3 eval/mock_agent_for_test.py {log_file}"
    
    # Create mock_agent_for_test.py
    mock_agent_code = f"""import sys, json, os
log_file = sys.argv[1]
invocations = []
if os.path.exists(log_file):
    with open(log_file, "r") as f:
        invocations = json.load(f)
invocations.append(sys.argv[2:])
with open(log_file, "w") as f:
    json.dump(invocations, f, indent=2)

# Write a failing benchmark_results.json on draft 1, success on draft 2
os.makedirs("logs", exist_ok=True)
if len(invocations) == 1:
    res = {{"results": [{{"task_id": "scaling_test_task_01", "status": "fail", "scope": "FAIL", "reason": "Unauthorized edit in forbidden.py", "unauthorized_edits": ["forbidden.py"], "test_logs": "AssertionError: 0 != 1"}}]}}
else:
    res = {{"results": [{{"task_id": "scaling_test_task_01", "status": "success", "scope": "PASS", "adherence": "PASS", "reason": "All checks passed"}}]}}

with open("logs/benchmark_results.json", "w") as f:
    json.dump(res, f)
"""
    with open("eval/mock_agent_for_test.py", "w") as f:
        f.write(mock_agent_code)

    try:
        ret, out, err = invoke_with_scaling(agent_cmd, str(task_file), variations=2)
        assert os.path.exists(log_file)
        with open(log_file, "r") as f:
            invocations = json.load(f)

        assert len(invocations) == 2, f"Expected 2 drafts before pass, got {len(invocations)}"
        
        # Draft 1 args (Temp = 0.0, no feedback)
        draft1_args = invocations[0]
        assert "--temperature" in draft1_args
        temp1_idx = draft1_args.index("--temperature")
        assert draft1_args[temp1_idx + 1] == "0.0"
        assert "--feedback" not in draft1_args

        # Draft 2 args (Temp = 0.35, includes feedback with SCOPE VIOLATION)
        draft2_args = invocations[1]
        assert "--temperature" in draft2_args
        temp2_idx = draft2_args.index("--temperature")
        assert draft2_args[temp2_idx + 1] == "0.35"
        assert "--feedback" in draft2_args
        fb_idx = draft2_args.index("--feedback")
        feedback_val = draft2_args[fb_idx + 1]
        assert "SCOPE VIOLATION" in feedback_val
        assert "forbidden.py" in feedback_val
        assert "AssertionError" in feedback_val

    finally:
        if os.path.exists("eval/mock_agent_for_test.py"):
            os.remove("eval/mock_agent_for_test.py")
