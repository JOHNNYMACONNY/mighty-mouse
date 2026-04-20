import yaml
import json
import sys
import os
import argparse
from gemini_client import GeminiClient
from response_parser import ResponseParser

def solve(p_cfg_path, task_input, feedback_str=None, workspace=None):
    # Set workspace if provided
    if workspace:
        if not os.path.exists(workspace): os.makedirs(workspace, exist_ok=True)
        os.chdir(workspace)

    # 1. Load Config
    with open(p_cfg_path, 'r') as f: p_cfg = yaml.safe_load(f)
    cfg_dir = os.path.dirname(os.path.abspath(p_cfg_path))
    
    # Assemble Prompt (Resolve relative to config file)
    segments = []
    for rel_path in p_cfg.get('prompt_segments', []):
        abs_p = os.path.join(cfg_dir, rel_path)
        if os.path.exists(abs_p):
            with open(abs_p, 'r') as f: segments.append(f.read())
            
    sys_prompt_rel = p_cfg.get('system_prompt_path', 'system_prompt.txt')
    abs_sys = os.path.join(cfg_dir, sys_prompt_rel)
    system_prompt = ""
    if os.path.exists(abs_sys):
        with open(abs_sys, 'r') as f: system_prompt = f.read()
    
    full_sys = "\n\n".join(segments + [system_prompt])

    # 2. Parse Task Input
    if os.path.exists(task_input):
        with open(task_input, 'r') as f:
            try:
                task_data = json.load(f)
                task_str = json.dumps(task_data, indent=2)
            except:
                with open(task_input, 'r') as f: task_str = f.read()
    else:
        task_str = task_input

    user_prompt = f"Implement the following task:\n{task_str}\n"
    if feedback_str:
        user_prompt += f"\n\nPREVIOUS ATTEMPT FAILED. FEEDBACK:\n{feedback_str}\n"

    # 3. Call Client
    client = GeminiClient()
    response = client.generate_content(full_sys, user_prompt)

    # 4. Parse and Write
    ResponseParser.parse_and_write(response)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("config")
    parser.add_argument("task")
    parser.add_argument("--feedback", help="Feedback from previous run")
    parser.add_argument("--workspace", help="Path to isolated workspace")
    args = parser.parse_args()
    
    # Resolve paths to absolute BEFORE chdir
    cfg_abs = os.path.abspath(args.config)
    task_abs = os.path.abspath(args.task)
    
    solve(cfg_abs, task_abs, feedback_str=args.feedback, workspace=args.workspace)
