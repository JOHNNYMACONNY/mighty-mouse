"""Task test execution verifier."""

from __future__ import annotations

import os
import subprocess
import tempfile


def run_task_tests(test_script: str) -> tuple[bool, str]:
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(test_script)
        temp_path = f.name

    try:
        res = subprocess.run(["python3", temp_path], capture_output=True, text=True, timeout=10)
        passed = (res.returncode == 0)
        logs = res.stdout + res.stderr
    except Exception as e:
        passed = False
        logs = str(e)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)
    return passed, logs
