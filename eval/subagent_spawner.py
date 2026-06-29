# DEPRECATED
import os
import subprocess
import sys
import json

def spawn_python_worker(script_content, name="worker.py"):
    """
    Spawns an autonomous Python worker script and executes it.
    The autoresearch loop can use this to execute multi-step formatting, linting, or cleanup passes.
    """
    with open(name, "w") as f:
        f.write(script_content)
    
    try:
        result = subprocess.run(["python3", name], capture_output=True, text=True, timeout=10)
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "stdout": "",
            "stderr": "Worker timeout after 10s."
        }
    finally:
        # Zero-Footprint: always delete the temp worker file after execution
        if os.path.exists(name):
            os.remove(name)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 subagent_spawner.py '<python_code>'")
        sys.exit(1)
    
    code = sys.argv[1]
    res = spawn_python_worker(code)
    print(json.dumps(res, indent=2))
