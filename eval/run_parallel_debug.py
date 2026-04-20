import os
import sys
import json
import subprocess
import shutil

TASK_DIR = "tasks/benchmark"
CONFIG = "configs/mighty_mouse_v1.yaml"

def main():
    root_dir = os.getcwd()
    env = dict(os.environ)
    env["PYTHONPATH"] = f"{root_dir}:{os.path.join(root_dir, 'src/orchestrator')}:{os.path.join(root_dir, 'eval')}"
    
    # Find task 201 specifically
    t_list = [os.path.join(TASK_DIR, f) for f in os.listdir(TASK_DIR) if "task_201_" in f]
    t = t_list[0]
    task_id = os.path.basename(t).replace(".json", "")
    task_abs = os.path.abspath(t)
    workspace = f"workspaces/debug_{task_id}"
    if not os.path.exists(workspace): os.makedirs(workspace, exist_ok=True)
    
    agent_abs = os.path.join(root_dir, "src/orchestrator/mighty_mouse_agent.py")
    verify_abs = os.path.join(root_dir, "eval/run_benchmark.py")
    config_abs = os.path.join(root_dir, CONFIG)
    
    print(f"[*] Debugging Task: {task_id}")
    print(f"[*] Agent: {agent_abs}")
    print(f"[*] Workspace: {workspace}")
    
    # 1. Agent
    res1 = subprocess.run([sys.executable, agent_abs, config_abs, task_abs], capture_output=True, text=True, cwd=workspace, env=env)
    print("--- AGENT STDOUT ---")
    print(res1.stdout)
    print("--- AGENT STDERR ---")
    print(res1.stderr)
    
    # 2. Verify
    res2 = subprocess.run([sys.executable, verify_abs, task_abs], capture_output=True, text=True, cwd=workspace, env=env)
    print("--- VERIFY STDOUT ---")
    print(res2.stdout)
    print("--- VERIFY STDERR ---")
    print(res2.stderr)

if __name__ == "__main__":
    main()
