import subprocess
import os
import sys

def check_adherence(checklist_path="CHECKLIST.md"):
    if not os.path.exists(checklist_path):
        return False, "CHECKLIST.md not found."
    
    try:
        package_root = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        script_path = os.path.join(package_root, "orchestrator", "enforce_workflow.py")
        res = subprocess.run([sys.executable, script_path, checklist_path], capture_output=True, text=True)
        
        passed = (res.returncode == 0)
        return passed, res.stdout + res.stderr
    except Exception as e:
        return False, str(e)
