import subprocess
import os

def check_adherence(checklist_path="CHECKLIST.md"):
    if not os.path.exists(checklist_path):
        return False, "CHECKLIST.md not found."
    
    root_dir = os.environ.get("PYTHONPATH", "").split(":")[0]
    enforcer = os.path.join(root_dir, 'src/orchestrator/enforce_workflow.py')
    
    res = subprocess.run(['python3', enforcer, checklist_path], capture_output=True, text=True)
    return (res.returncode == 0), res.stdout + res.stderr
