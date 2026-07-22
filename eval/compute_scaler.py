import os
import subprocess
import json
import shlex

def run_command(cmd, cwd="."):
    if isinstance(cmd, str):
        cmd = shlex.split(cmd)
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
    return result.returncode, result.stdout, result.stderr

def extract_feedback_from_results(task_id, fallback_stderr=""):
    """
    Extracts failure tracebacks, scope errors, and adherence logs from benchmark results.
    Truncates output to maintain a high signal-to-noise ratio (~1500 chars max).
    """
    if not os.path.exists("logs/benchmark_results.json"):
        if fallback_stderr:
            lines = fallback_stderr.strip().split("\n")
            return "RUNTIME ERROR:\n" + "\n".join(lines[-20:])[:1200]
        return "Task failed during execution."

    try:
        with open("logs/benchmark_results.json", "r") as f:
            res_data = json.load(f)
            res_list = res_data if isinstance(res_data, list) else res_data.get("results", [])
            target_res = next((r for r in res_list if isinstance(r, dict) and r.get("task_id") == task_id), None)
            
            if not target_res:
                return "Task verification missing in results."

            feedback_parts = []
            if target_res.get("scope") != "PASS":
                reason = target_res.get("reason", "Scope verification failed")
                edits = target_res.get("unauthorized_edits", [])
                edit_str = f" Unauthorized edits: {edits}" if edits else ""
                feedback_parts.append(f"SCOPE VIOLATION: {reason}.{edit_str}")

            if target_res.get("adherence") != "PASS":
                adh_logs = target_res.get("adherence_logs", "")
                if adh_logs:
                    feedback_parts.append(f"ADHERENCE VIOLATION:\n{adh_logs[:400]}")

            test_logs = target_res.get("test_logs", "")
            if test_logs and target_res.get("status") != "success":
                lines = test_logs.strip().split("\n")
                short_logs = "\n".join(lines[-25:])
                feedback_parts.append(f"TEST FAILURE:\n{short_logs[:1000]}")

            if feedback_parts:
                return "\n".join(feedback_parts)
            
            return target_res.get("reason", "Verification failed")
    except Exception as e:
        return f"Execution error: {e}"

def invoke_with_scaling(agent_cmd, task_path, variations=3):
    """
    Implements Test-Time Compute Scaling (o1 pattern) with:
      - Execution feedback loop across attempts.
      - Temperature annealing (T=0.0 -> 0.35 -> 0.70).
      - Best-of-N consensus selection.
    """
    best_ret, best_out, best_err = None, "", ""
    last_feedback = None

    with open(task_path, 'r') as f:
        task_data = json.load(f)
    current_id = task_data.get('id')

    # Convert agent_cmd to list if it's a string
    base_cmd = shlex.split(agent_cmd) if isinstance(agent_cmd, str) else list(agent_cmd)

    passing_candidates = []

    for i in range(variations):
        temp = round(min(0.0 + i * 0.35, 0.70), 2)
        print(f"  [Compute Scaler] Running draft {i+1}/{variations} (Temp={temp})...")

        # Reset workspace
        subprocess.run(["bash", "eval/reset_workspace.sh"])

        # Construct variation command with temperature & feedback
        cmd_tokens = list(base_cmd)
        cmd_tokens.extend(["--temperature", str(temp)])
        if last_feedback:
            cmd_tokens.extend(["--feedback", last_feedback])

        # Invoke agent
        ret, out, err = run_command(cmd_tokens)

        # Verify internally
        subprocess.run(["python3", "src/mighty_mouse/services/verifiers/run_benchmark.py", task_path], capture_output=True)

        if os.path.exists("logs/benchmark_results.json"):
            with open("logs/benchmark_results.json", "r") as f:
                res = json.load(f)
                res_list = res if isinstance(res, list) else res.get("results", [])
                success = False
                for r in res_list:
                    if isinstance(r, dict) and r.get('task_id') == current_id:
                        if r.get('status') == 'success':
                            success = True
                        break

                if success:
                    # Calculate diff size for consensus ranking
                    diff_proc = subprocess.run(["git", "diff", "--numstat"], capture_output=True, text=True)
                    diff_lines = 0
                    for line in diff_proc.stdout.splitlines():
                        parts = line.strip().split()
                        if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
                            diff_lines += int(parts[0]) + int(parts[1])

                    print(f"  [Compute Scaler] Draft {i+1} PASSED (Diff: {diff_lines} lines). Stashing candidate.")
                    passing_candidates.append({
                        "draft": i + 1,
                        "ret": ret,
                        "out": out,
                        "err": err,
                        "diff_lines": diff_lines,
                        "temp": temp
                    })
                    # Lock in first pass if early exit is desired, or evaluate full set
                    if len(passing_candidates) == 1:
                        best_ret, best_out, best_err = ret, out, err

        # Extract feedback for next variation
        last_feedback = extract_feedback_from_results(current_id, fallback_stderr=err)
        if not passing_candidates:
            best_ret, best_out, best_err = ret, out, err
        print(f"  [Compute Scaler] Draft {i+1} completed with feedback ({last_feedback[:100]}...).")

    if passing_candidates:
        passing_candidates.sort(key=lambda c: c["diff_lines"])
        best_candidate = passing_candidates[0]
        print(f"  [Compute Scaler] Best-of-{len(passing_candidates)} Consensus Selected: Draft {best_candidate['draft']} (Minimal Diff: {best_candidate['diff_lines']} lines, Temp={best_candidate['temp']}). Locking in timeline.")
        return best_candidate["ret"], best_candidate["out"], best_candidate["err"]

    print(f"  [Compute Scaler] Exhausted {variations} variations. Yielding last attempt.")
    return best_ret, best_out, best_err

