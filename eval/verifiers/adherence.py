import subprocess
import os

def check_adherence(checklist_path="CHECKLIST.md"):
    if not os.path.exists(checklist_path):
        return False, "CHECKLIST.md not found."
    res = subprocess.run(['python3', 'src/orchestrator/enforce_workflow.py', checklist_path], capture_output=True, text=True)
    return (res.returncode == 0), res.stdout + res.stderr
