import os
import json
import tempfile
import shutil
from eval.compute_scaler import extract_feedback_from_results, invoke_with_scaling

def test_extract_feedback_fallback():
    if os.path.exists("logs/benchmark_results.json"):
        os.remove("logs/benchmark_results.json")
    fb = extract_feedback_from_results("task_123", fallback_stderr="Traceback (most recent call last):\n  File 'test.py', line 5, in <module>\nAssertionError: Expected 42")
    assert "RUNTIME ERROR" in fb
    assert "AssertionError" in fb

def test_extract_feedback_scope_and_test_failure():
    os.makedirs("logs", exist_ok=True)
    results = {
        "results": [
            {
                "task_id": "task_scope_fail",
                "status": "fail",
                "scope": "FAIL",
                "reason": "Scope verification failed: forbidden edit",
                "unauthorized_edits": ["secret.py"],
                "test_logs": "FAILED test_main.py::test_calc - AssertionError: 1 != 2"
            }
        ]
    }
    with open("logs/benchmark_results.json", "w") as f:
        json.dump(results, f)

    fb = extract_feedback_from_results("task_scope_fail")
    assert "SCOPE VIOLATION" in fb
    assert "secret.py" in fb
    assert "TEST FAILURE" in fb
