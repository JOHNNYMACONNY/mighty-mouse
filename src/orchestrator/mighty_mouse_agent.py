import argparse
import json
import os
import sys

import yaml

from gemini_client import GeminiClient
from response_parser import ResponseParser


def _write_run_metadata(client, workspace, task_input, feedback_str=None, extra=None):
    logs_dir = os.path.join(workspace or os.getcwd(), "logs")
    os.makedirs(logs_dir, exist_ok=True)
    metadata = dict(client.last_metadata)
    metadata.update(
        {
            "task_input": task_input,
            "workspace": workspace or os.getcwd(),
            "feedback_supplied": bool(feedback_str),
        }
    )
    if extra:
        metadata.update(extra)
    with open(os.path.join(logs_dir, "last_agent_run.json"), "w") as f:
        json.dump(metadata, f, indent=2)


def solve(p_cfg_path, task_input, feedback_str=None, workspace=None):
    task_data = None
    if workspace:
        if not os.path.exists(workspace):
            os.makedirs(workspace, exist_ok=True)
        os.chdir(workspace)

    with open(p_cfg_path, 'r') as f:
        p_cfg = yaml.safe_load(f)
    cfg_dir = os.path.dirname(os.path.abspath(p_cfg_path))

    segments = []
    for rel_path in p_cfg.get('prompt_segments', []):
        abs_p = os.path.join(cfg_dir, rel_path)
        if os.path.exists(abs_p):
            with open(abs_p, 'r') as f:
                segments.append(f.read())

    sys_prompt_rel = p_cfg.get('system_prompt_path', 'system_prompt.txt')
    abs_sys = os.path.join(cfg_dir, sys_prompt_rel)
    system_prompt = ""
    if os.path.exists(abs_sys):
        with open(abs_sys, 'r') as f:
            system_prompt = f.read()

    full_sys = "\n\n".join(segments + [system_prompt])

    if os.path.exists(task_input):
        with open(task_input, 'r') as f:
            try:
                task_data = json.load(f)
                task_str = json.dumps(task_data, indent=2)
            except Exception:
                with open(task_input, 'r') as f2:
                    task_str = f2.read()
    else:
        task_str = task_input

    user_prompt = f"Implement the following task:\n{task_str}\n"
    if feedback_str:
        user_prompt += f"\n\nPREVIOUS ATTEMPT FAILED. FEEDBACK:\n{feedback_str}\n"

    client = GeminiClient(config=p_cfg)
    response = client.generate_content(full_sys, user_prompt)
    allowed_delete_paths = []
    if isinstance(task_data, dict):
        allowed_delete_paths = task_data.get("deletable_files", [])
    output_paths = ResponseParser.parse_and_write(
        response,
        workspace_root=workspace or os.getcwd(),
        allowed_delete_paths=allowed_delete_paths,
    )
    workspace_root = workspace or os.getcwd()
    deleted_files = [
        path for path in output_paths
        if path in allowed_delete_paths and not os.path.exists(os.path.join(workspace_root, path))
    ]
    written_files = [path for path in output_paths if path not in deleted_files]
    _write_run_metadata(
        client,
        workspace,
        task_input,
        feedback_str,
        extra={
            "task_id": task_data.get("id") if isinstance(task_data, dict) else None,
            "output_files": output_paths,
            "written_files": written_files,
            "deleted_files": deleted_files,
        },
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("config")
    parser.add_argument("task")
    parser.add_argument("--feedback", help="Feedback from previous run")
    parser.add_argument("--workspace", help="Path to isolated workspace")
    args = parser.parse_args()

    cfg_abs = os.path.abspath(args.config)
    task_abs = os.path.abspath(args.task)

    solve(cfg_abs, task_abs, feedback_str=args.feedback, workspace=args.workspace)
