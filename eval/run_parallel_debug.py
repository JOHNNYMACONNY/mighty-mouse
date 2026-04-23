import os
import sys
import json
import subprocess
import shutil

import argparse

TASK_DIR = "tasks/benchmark"
CONFIG = "configs/mighty_mouse_v1.yaml"

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tier", help="Tier to pick a task from")
    parser.add_argument("--task", help="Specific task ID")
    args = parser.parse_args()

    root_dir = os.getcwd()
    env = dict(os.environ)
    env["PYTHONPATH"] = f"{root_dir}:{os.path.join(root_dir, 'src/orchestrator')}:{os.path.join(root_dir, 'eval')}"
    
    # Selection logic
    if args.task:
        target = args.task
    elif args.tier:
        t = int(args.tier)
        # 100-based tiers: T1:1, T2:101, T3:201, T4:301, T5:401, T6:501, T7:651, T8:801
        start = {1:1, 2:101, 3:201, 4:301, 5:401, 6:501, 7:651, 8:801}.get(t, 1)
        target = f"task_{start:03d}"
    else:
        target = "task_201"

    t_list = [os.path.join(TASK_DIR, f) for f in os.listdir(TASK_DIR) if target in f]
    if not t_list:
        print(f"Error: Task matching {target} not found.")
        return
    
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
    
    # 2. Verify (Passing workspace for drift check)
    res2 = subprocess.run([sys.executable, verify_abs, task_abs], capture_output=True, text=True, cwd=workspace, env=env)
    print("--- VERIFY STDOUT ---")
    print(res2.stdout)
    print("--- VERIFY STDERR ---")
    print(res2.stderr)

if __name__ == "__main__":
    main()
