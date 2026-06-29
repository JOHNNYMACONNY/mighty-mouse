import subprocess
import os
import sys

def check_adherence(checklist_path="CHECKLIST.md"):
    if not os.path.exists(checklist_path):
        return False, "CHECKLIST.md not found."
    
    try:
        cwd = os.getcwd()
        if 'workspaces/' in cwd:
            project_root = os.path.abspath(os.path.join(cwd, "../.."))
        else:
            project_root = os.path.abspath(cwd)
            
        script_path = os.path.join(project_root, "src/mighty_mouse/orchestrator/enforce_workflow.py")
        res = subprocess.run([sys.executable, script_path, checklist_path], capture_output=True, text=True)
        
        passed = (res.returncode == 0)
        return passed, res.stdout + res.stderr
    except Exception as e:
        return False, str(e)
