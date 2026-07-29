"""Task test execution verifier."""

from __future__ import annotations

import os
import subprocess


def run_task_tests(test_script: str) -> tuple[bool, str]:
    with open('test_runner.py', 'w') as f:
        f.write(test_script)
    try:
        res = subprocess.run(['python3', 'test_runner.py'], capture_output=True, text=True, timeout=10)
        passed = (res.returncode == 0)
        logs = res.stdout + res.stderr
    except Exception as e:
        passed = False
        logs = str(e)
    finally:
        if os.path.exists('test_runner.py'):
            os.remove('test_runner.py')
    return passed, logs
