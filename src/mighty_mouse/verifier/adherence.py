"""Protocol adherence verifier."""

from __future__ import annotations

import os
import subprocess
import sys


def check_adherence(checklist_path: str = "CHECKLIST.md", cwd: str | None = None) -> tuple[bool, str]:
    abs_checklist_path = os.path.abspath(checklist_path)
    if not os.path.exists(abs_checklist_path):
        return False, f"Checklist file not found: {checklist_path}"

    try:
        package_root = os.path.dirname(
            os.path.dirname(os.path.abspath(__file__))
        )
        script_path = os.path.join(package_root, "orchestrator", "enforce_workflow.py")
        exec_cwd = cwd if cwd else os.path.dirname(abs_checklist_path)
        res = subprocess.run([sys.executable, script_path, abs_checklist_path], capture_output=True, text=True, cwd=exec_cwd)

        passed = (res.returncode == 0)
        return passed, res.stdout + res.stderr
    except Exception as e:
        return False, str(e)
