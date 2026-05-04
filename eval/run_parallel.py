import concurrent.futures
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime

import yaml

TASK_DIR = "tasks/benchmark"
LOG_PATH = "logs/benchmark_results.json"
MAX_WORKERS = 5
CONFIG = "configs/mighty_mouse_v1.yaml"


def _load_config():
    with open(CONFIG, "r") as f:
        return yaml.safe_load(f)


def _assert_live_benchmark_config(cfg):
    provider = cfg.get("provider", "auto")
    if provider == "sim" or cfg.get("allow_simulation"):
        raise RuntimeError(
            "Benchmark config must use a live provider. Simulation is dev-only and must not be used for benchmark trials."
        )


def run_task(task_path):
    cfg = _load_config()
    task_id = os.path.basename(task_path).replace(".json", "")
    task_abs = os.path.abspath(task_path)
    root_dir = os.getcwd()
    workspace = os.path.join(root_dir, f"workspaces/{task_id}")

    config_abs = os.path.join(root_dir, CONFIG)
    agent_abs = os.path.join(root_dir, "src/orchestrator/mighty_mouse_agent.py")
    verify_abs = os.path.join(root_dir, "eval/run_benchmark.py")

    if os.path.exists(workspace):
        shutil.rmtree(workspace)
    os.makedirs(workspace, exist_ok=True)

    success = False
    feedback = "No feedback"
    round_logs = []

    try:
        env = dict(os.environ)
        env["PYTHONPATH"] = f"{root_dir}:{os.path.join(root_dir, 'src/orchestrator')}:{os.path.join(root_dir, 'eval')}"

        with open(task_abs, 'r') as f:
            t_data = json.load(f)
            primary = t_data['expected_files'][0]
            for extra_f in t_data['expected_files'][1:]:
                with open(os.path.join(workspace, extra_f), 'w') as ef:
                    ef.write("def corrupted_logic(): pass (SYNTAX_ERROR)\nimport non_existent_pkg")

        for r in range(1, 3):
            cmd = [sys.executable, agent_abs, config_abs, task_abs]
            if r > 1:
                cmd.extend(["--feedback", feedback])

            started = time.time()
            agent_res = subprocess.run(cmd, capture_output=True, text=True, cwd=workspace, env=env, timeout=300)

            run_metadata = {}
            metadata_path = os.path.join(workspace, "logs", "last_agent_run.json")
            if os.path.exists(metadata_path):
                try:
                    with open(metadata_path, "r") as f:
                        run_metadata = json.load(f)
                except Exception:
                    run_metadata = {"metadata_read_error": True}

            sandbox_abs = os.path.join(root_dir, "eval/sandbox_wrapper.py")
            ver_res = subprocess.run(
                [sys.executable, sandbox_abs, verify_abs, task_abs],
                capture_output=True,
                text=True,
                cwd=workspace,
                env=env,
            )
            duration = round(time.time() - started, 3)
            round_logs.append(
                {
                    "round": r,
                    "duration_sec": duration,
                    "agent_returncode": agent_res.returncode,
                    "agent_stdout": agent_res.stdout,
                    "agent_stderr": agent_res.stderr,
                    "run_metadata": run_metadata,
                    "verify_stdout": ver_res.stdout,
                    "verify_stderr": ver_res.stderr,
                }
            )

            if "success" in ver_res.stdout.lower():
                success = True
                break
            feedback = ver_res.stdout if ver_res.stdout else "Verification failed"

        # Aggregate metrics from rounds
        total_p_tokens = 0
        total_c_tokens = 0
        for r in round_logs:
            run_meta = r.get("run_metadata") or {}
            usage_hist = run_meta.get("usage_history")
            if usage_hist:
                # Sum up all internal attempts within this round
                total_p_tokens += sum((u.get("usage") or {}).get("prompt_tokens") or 0 for u in usage_hist)
                total_c_tokens += sum((u.get("usage") or {}).get("completion_tokens") or 0 for u in usage_hist)
            else:
                # Fallback to single usage
                usage = run_meta.get("usage") or {}
                total_p_tokens += usage.get("prompt_tokens") or 0
                total_c_tokens += usage.get("completion_tokens") or 0

        total_latency = sum(r.get("duration_sec") or 0 for r in round_logs)

        # Detect if any round had a schema error
        has_schema_error = any(r["run_metadata"].get("schema_error") for r in round_logs)
        
        reason = feedback if not success else None
        if not success and has_schema_error:
            reason = "Schema Error: No files found"

        result = {
            "task_id": task_id,
            "status": "success" if success else "fail",
            "reason": reason,
            "timestamp": datetime.now().isoformat(),
            "provider": cfg.get("provider"),
            "model": cfg.get("model"),
            "usage": {
                "total_prompt_tokens": total_p_tokens,
                "total_completion_tokens": total_c_tokens,
                "total_total_tokens": total_p_tokens + total_c_tokens,
            },
            "latency_seconds": round(total_latency, 3),
            "rounds": round_logs,
        }
        if success:
            shutil.rmtree(workspace, ignore_errors=True)
        return result
    except Exception as e:
        # shutil.rmtree(workspace, ignore_errors=True)
        return {
            "task_id": task_id,
            "status": "fail",
            "reason": str(e),
            "timestamp": datetime.now().isoformat(),
            "provider": cfg.get("provider"),
            "model": cfg.get("model"),
            "rounds": round_logs,
        }


def main(tier=None):
    cfg = _load_config()
    _assert_live_benchmark_config(cfg)

    if not os.path.exists("logs"):
        os.makedirs("logs")
    if not os.path.exists("workspaces"):
        os.makedirs("workspaces")

    if tier:
        config_path = "eval/evaluation_config.json"
        if not os.path.exists(config_path):
            print(f"Error: Config path {config_path} not found.")
            return
        with open(config_path, 'r') as f:
            tier_config = json.load(f)
        tasks_to_run = tier_config["tiers"].get(tier, [])
        if tasks_to_run == "all":
            all_files = [f for f in os.listdir(TASK_DIR) if f.endswith(".json") and not f.startswith(".")]
            tasks = [os.path.join(TASK_DIR, f) for f in sorted(all_files)]
        else:
            tasks = [os.path.join(TASK_DIR, f) for f in tasks_to_run]
    else:
        all_files = [f for f in os.listdir(TASK_DIR) if f.endswith(".json") and not f.startswith(".")]
        tasks = [os.path.join(TASK_DIR, f) for f in sorted(all_files)]

    print(f"[*] Dispatching {len(tasks)} tasks with provider={cfg.get('provider')} model={cfg.get('model')}...")
    results = []
    with concurrent.futures.ProcessPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(run_task, t): t for t in tasks}
        for future in concurrent.futures.as_completed(futures):
            results.append(future.result())
            time.sleep(5)  # Safe throttle

    # Summary calculations
    success_count = len([r for r in results if r["status"] == "success"])
    total_prompt = sum(r.get("usage", {}).get("total_prompt_tokens", 0) for r in results)
    total_completion = sum(r.get("usage", {}).get("total_completion_tokens", 0) for r in results)
    avg_latency = round(sum(r.get("latency_seconds", 0) for r in results) / len(results), 3) if results else 0

    final_payload = {
        "summary": {
            "success_rate": f"{success_count}/{len(results)}",
            "total_prompt_tokens": total_prompt,
            "total_completion_tokens": total_completion,
            "total_tokens": total_prompt + total_completion,
            "avg_latency_sec": avg_latency,
            "timestamp": datetime.now().isoformat(),
        },
        "results": results
    }

    with open(LOG_PATH, "w") as f:
        json.dump(final_payload, f, indent=2)

    success_count = len([r for r in results if r["status"] == "success"])
    print(f"[*] Done. Success: {success_count}/{len(results)}")


if __name__ == "__main__":
    main()
