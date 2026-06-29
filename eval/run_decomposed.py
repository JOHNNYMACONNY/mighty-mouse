# DEPRECATED
import argparse
import json
import os
import sys
import time
import yaml
from datetime import datetime

# Add src/mighty_mouse/orchestrator to path
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.join(_REPO_ROOT, "src", "mighty_mouse", "orchestrator"))
from gemini_client import GeminiClient
from response_parser import ResponseParser
from analyze_failure import get_category

def run_decomposed(config_path, task_path, workspace):
    import sys
    def log(msg):
        print(msg, file=sys.stderr)

    with open(config_path, 'r') as f:
        cfg = yaml.safe_load(f)
    
    with open(task_path, 'r') as f:
        task_data = json.load(f)
    
    client = GeminiClient(config=cfg)
    task_id = task_data.get('id', 'unknown')
    
    # Harness-owned state directory
    mighty_dir = os.path.join(workspace, ".mighty")
    os.makedirs(mighty_dir, exist_ok=True)
    plan_path = os.path.join(mighty_dir, "PLAN.md")

    # Pass 1: Planning
    log(f"[*] Pass 1 (Planning) for {task_id}...")
    plan_prompt = (
        "ANALYZE THE TASK BELOW AND EMIT A PLAN.md WITH THE FOLLOWING METADATA HEADER:\n"
        "target_files: [list]\n"
        "expected_files: [list]\n"
        "forbidden_files: [list]\n"
        "required_checks: [list]\n"
        "risk_notes: [text]\n\n"
        "DO NOT WRITE ANY IMPLEMENTATION CODE YET.\n"
        "ONLY OUTPUT THE PLAN.md AS A CODE BLOCK: ```text:.mighty/PLAN.md\n...\n```\n\n"
        f"TASK:\n{json.dumps(task_data, indent=2)}"
    )
    
    start_p1 = time.time()
    pass_1_status = "success"
    pass_1_tokens = 0
    try:
        p1_res = client.generate_content("", plan_prompt)
        latency_p1 = time.time() - start_p1
        pass_1_tokens = client.last_metadata.get("usage", {}).get("total_tokens", 0)
        # Extract .mighty/PLAN.md (system_mode=True allows writing to hidden harness dir)
        ResponseParser.parse_and_write(p1_res, workspace_root=workspace, system_mode=True)
        has_plan = os.path.exists(plan_path)
    except Exception as e:
        return {
            "status": "fail", "reason": f"Pass 1 Error: {str(e)}", "category": "PARSER",
            "pass_1_status": "error", "pass_1_latency": round(time.time() - start_p1, 2),
            "pass_2_status": "skipped"
        }

    if not has_plan:
        return {
            "status": "fail", "reason": "Pass 1 failed to emit .mighty/PLAN.md", "category": "PARSER",
            "pass_1_status": "fail", "pass_1_latency": round(latency_p1, 2),
            "pass_2_status": "skipped"
        }

    # Pass 2: Implementation
    log(f"[*] Pass 2 (Implementation) for {task_id}...")
    with open(plan_path, 'r') as f:
        plan_content = f.read()
    
    impl_prompt = (
        f"IMPLEMENT THE TASK ACCORDING TO THIS PLAN:\n\n<plan>\n{plan_content}\n</plan>\n\n"
        f"NOTE: The original Task JSON below is the source of truth. The plan is for guidance.\n\n"
        f"TASK DATA:\n{json.dumps(task_data, indent=2)}"
    )
    
    start_p2 = time.time()
    pass_2_status = "success"
    pass_2_tokens = 0
    try:
        p2_res = client.generate_content("", impl_prompt)
        latency_p2 = time.time() - start_p2
        pass_2_tokens = client.last_metadata.get("usage", {}).get("total_tokens", 0)
        output_paths = ResponseParser.parse_and_write(p2_res, workspace_root=workspace)
    except Exception as e:
        return {
            "status": "fail", "reason": f"Pass 2 Error: {str(e)}", "category": "PARSER",
            "pass_1_status": "success", "pass_1_latency": round(latency_p1, 2), "pass_1_tokens": pass_1_tokens,
            "pass_2_status": "error", "pass_2_latency": round(time.time() - start_p2, 2)
        }

    # Verification
    log(f"[*] Verifying {task_id}...")
    verify_script = os.path.join(os.getcwd(), "eval/run_benchmark.py")
    sandbox_wrapper = os.path.join(os.getcwd(), "eval/sandbox_wrapper.py")
    
    env = dict(os.environ)
    env["PYTHONPATH"] = f"{os.getcwd()}:{os.path.join(os.getcwd(), 'src/mighty_mouse/orchestrator')}:{os.path.join(os.getcwd(), 'eval')}"
    
    import subprocess
    ver_res = subprocess.run(
        [sys.executable, sandbox_wrapper, verify_script, task_path],
        capture_output=True, text=True, cwd=workspace, env=env
    )
    
    success = "task success" in ver_res.stdout.lower()
    
    # Filter out harness-internal files from metadata
    final_files = [p for p in output_paths if not p.startswith(".mighty/")]

    return {
        "status": "success" if success else "fail",
        "category": "LOGIC" if not success else "SUCCESS",
        "reason": ver_res.stdout if not success else None,
        "latency_seconds": round(latency_p1 + latency_p2, 2),
        "pass_1_status": pass_1_status,
        "pass_1_latency": round(latency_p1, 2),
        "pass_1_tokens": pass_1_tokens,
        "pass_2_status": pass_2_status,
        "pass_2_latency": round(latency_p2, 2),
        "pass_2_tokens": pass_2_tokens,
        "files_touched": final_files,
        "verification_status": "Passed" if success else "Failed"
    }

if __name__ == "__main__":
    # Minimal CLI for run_spike.py to call
    parser = argparse.ArgumentParser()
    parser.add_argument("--config")
    parser.add_argument("--task")
    parser.add_argument("--workspace")
    args = parser.parse_args()
    
    config_abs = os.path.abspath(args.config)
    task_abs = os.path.abspath(args.task)
    workspace_abs = os.path.abspath(args.workspace)
    
    result = run_decomposed(config_abs, task_abs, workspace_abs)
    # The ONLY output to stdout
    print(json.dumps(result))
