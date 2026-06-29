import concurrent.futures
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime
import yaml

# Centralized failure analysis
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.join(_REPO_ROOT, "src", "mighty_mouse", "orchestrator"))

def get_category(stderr_str, stdout_str, status_str):
    if status_str == "success":
        return "SUCCESS"
    err = (stderr_str or "").lower() + (stdout_str or "").lower()
    if "syntaxerror" in err:
        return "SYNTAX_ERROR"
    if "importerror" in err or "modulenotfounderror" in err:
        return "IMPORT_ERROR"
    return "TEST_FAILURE"

TASK_DIR = "tasks/benchmark"
LOG_PATH = "logs/benchmark_results.json"
MAX_WORKERS_DEFAULT = 4
from importlib import resources

def _get_default_config():
    try:
        return str(resources.files("mighty_mouse.resources.configs").joinpath("mighty_mouse_v2_lean.yaml"))
    except:
        return "configs/mighty_mouse_v2_lean.yaml"

DEFAULT_CONFIG = _get_default_config()


def _load_config(config_path=None):
    path = config_path or DEFAULT_CONFIG
    with open(path, "r") as f:
        return yaml.safe_load(f)


def _assert_live_benchmark_config(cfg):
    provider = cfg.get("provider", "auto")
    if provider == "sim" or cfg.get("allow_simulation"):
        raise RuntimeError(
            "Benchmark config must use a live provider. Simulation is dev-only and must not be used for benchmark trials."
        )


def run_task(
    task_path,
    variant="lean",
    config_path=None,
    trials=2,
    cleanup=True,
    skills=None,
    output_dir=None,
):
    cfg = _load_config(config_path)
    task_id = os.path.basename(task_path).replace(".json", "")
    task_abs = os.path.abspath(task_path)
    root_dir = os.getcwd()
    output_root = os.path.abspath(output_dir or tempfile.mkdtemp(prefix="mighty_mouse_"))
    workspace = os.path.join(output_root, "workspaces", task_id)

    config_abs = os.path.abspath(config_path or DEFAULT_CONFIG)
    mighty_mouse_pkg = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    agent_abs = os.path.join(mighty_mouse_pkg, "orchestrator", "mighty_mouse_agent.py")
    verify_abs = os.path.join(mighty_mouse_pkg, "services", "verifiers", "run_benchmark.py")
    sandbox_abs = os.path.join(mighty_mouse_pkg, "services", "verifiers", "sandbox_wrapper.py")
    hybrid_runner_abs = os.path.join(root_dir, "eval/run_hybrid.py")

    if os.path.exists(workspace):
        shutil.rmtree(workspace)
    os.makedirs(workspace, exist_ok=True)
    workspace_task_path = os.path.join(workspace, os.path.basename(task_abs))
    shutil.copy2(task_abs, workspace_task_path)

    success = False
    feedback = "No feedback"
    round_logs = []

    try:
        env = dict(os.environ)
        env["PYTHONPATH"] = f"{root_dir}:{mighty_mouse_pkg}:{os.path.join(mighty_mouse_pkg, 'services')}"

        with open(task_abs, 'r') as f:
            t_data = json.load(f)
            # Copy fixtures if specified
            fixture_dir = t_data.get("fixture_dir")
            if fixture_dir:
                fixture_abs = os.path.join(root_dir, fixture_dir)
                if os.path.exists(fixture_abs):
                    for item in os.listdir(fixture_abs):
                        s = os.path.join(fixture_abs, item)
                        d = os.path.join(workspace, item)
                        if os.path.isdir(s):
                            shutil.copytree(s, d)
                        else:
                            shutil.copy(s, d)

            expected = t_data.get('expected_files', [])
            if expected:
                for extra_f in expected[1:]:
                    target_path = os.path.join(workspace, extra_f)
                    if not os.path.exists(target_path):
                        with open(target_path, 'w') as ef:
                            ef.write("def corrupted_logic(): pass (SYNTAX_ERROR)\nimport non_existent_pkg")

        # Hybrid Branch
        if variant == "hybrid":
            env["MIGHTY_RESEARCH_MODE"] = "1"
            cmd = [sys.executable, hybrid_runner_abs, "--config", config_abs, "--task", task_abs, "--workspace", workspace, "--trials", str(trials)]
            started = time.time()
            proc = subprocess.run(cmd, capture_output=True, text=True, env=env)
            try:
                res_data = json.loads(proc.stdout)
                res_data["timestamp"] = datetime.now().isoformat()
                return res_data
            except:
                return {"task_id": task_id, "status": "fail", "reason": "Hybrid runner failed", "stdout": proc.stdout, "stderr": proc.stderr}

        for r in range(1, trials + 1):
            cmd = [sys.executable, agent_abs, config_abs, task_abs]
            if r > 1:
                cmd.extend(["--feedback", feedback])
            
            if skills:
                cmd.extend(["--skills", skills])

            started = time.time()
            try:
                agent_res = subprocess.run(cmd, capture_output=True, text=True, cwd=workspace, env=env, timeout=300)
                agent_returncode = agent_res.returncode
                agent_stdout = agent_res.stdout
                agent_stderr = agent_res.stderr
                timeout_occurred = False
            except subprocess.TimeoutExpired as te:
                agent_returncode = -1
                agent_stdout = te.stdout.decode() if te.stdout else "Timeout before stdout capture"
                agent_stderr = te.stderr.decode() if te.stderr else "Timeout before stderr capture"
                timeout_occurred = True
                print(f"[!] Agent TIMED OUT for {task_id} (Round {r}) after 300s")

            if not timeout_occurred and agent_returncode != 0:
                print(f"[!] Agent crashed for {task_id} (Round {r}):")
                print(agent_res.stdout)
                print(agent_res.stderr)

            run_metadata = {}
            metadata_path = os.path.join(workspace, "logs", "last_agent_run.json")
            if os.path.exists(metadata_path):
                try:
                    with open(metadata_path, "r") as f:
                        run_metadata = json.load(f)
                except Exception:
                    run_metadata = {"metadata_read_error": True}

            if not timeout_occurred:
                ver_res = subprocess.run(
                    [sys.executable, sandbox_abs, verify_abs, workspace_task_path],
                    capture_output=True,
                    text=True,
                    cwd=workspace,
                    env=env,
                )
                verify_stdout = ver_res.stdout
                verify_stderr = ver_res.stderr
            else:
                verify_stdout = f"FAIL: Task timed out after 300s"
                verify_stderr = ""

            verify_json = None
            try:
                # Find the JSON block in the output
                if "{" in verify_stdout and "}" in verify_stdout:
                    json_str = verify_stdout[verify_stdout.find("{"):verify_stdout.rfind("}")+1]
                    verify_json = json.loads(json_str)
            except Exception:
                pass

            duration = round(time.time() - started, 3)
            round_logs.append(
                {
                    "round": r,
                    "duration_sec": duration,
                    "agent_returncode": agent_returncode,
                    "agent_stdout": agent_stdout,
                    "agent_stderr": agent_stderr,
                    "run_metadata": run_metadata,
                    "verify_stdout": verify_stdout,
                    "verify_stderr": verify_stderr,
                    "verify_json": verify_json,
                    "timeout": timeout_occurred
                }
            )

            is_success = False
            if not timeout_occurred:
                if verify_json:
                    is_success = verify_json.get("status") == "success"
                else:
                    # Fallback to string matching, but be more specific
                    is_success = f"task {task_id} success" in verify_stdout.lower()

            if is_success:
                success = True
                break
            
            if verify_json:
                feedback = verify_json.get("reason", "Verification failed")
            else:
                feedback = verify_stdout if verify_stdout else "Verification failed"

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
        
        # Categorization logic
        timeout_in_any_round = any(r.get("timeout") for r in round_logs)
        
        reason = feedback if not success else None
        
        if not success:
            if timeout_in_any_round:
                reason = "TIMEOUT: Agent exceeded 300s budget"
                category = "TIMEOUT"
            else:
                category = get_category(reason, "", "fail")
        else:
            category = "SUCCESS"

        result = {
            "task_id": task_id,
            "status": "success" if success else "fail",
            "category": category,
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
            "skill_ids": run_metadata.get("skill_ids", []),
            "overlay_enabled": run_metadata.get("overlay_enabled", False),
            "rounds": round_logs,
        }
        
        # Bubble up telemetry from last round for easier analysis
        if round_logs:
            last_round = round_logs[-1]
            last_verify = last_round.get("verify_json") or {}
            last_meta = last_round.get("run_metadata") or {}
            result["telemetry"] = {
                "stale_ghost_files_removed_pre_run": last_meta.get("stale_ghost_files_removed_pre_run", 0),
                "ghost_files_flagged_post_run": last_verify.get("ghost_files_flagged_post_run", []),
                "fixture_files_preserved": last_verify.get("fixture_files_preserved", 0),
                "harness_files_ignored": last_verify.get("harness_files_ignored", 0),
                "scope_status": last_verify.get("scope_status", "UNKNOWN")
            }

        return result
    except Exception as e:
        return {
            "task_id": task_id,
            "status": "fail",
            "reason": str(e),
            "timestamp": datetime.now().isoformat(),
            "provider": cfg.get("provider"),
            "model": cfg.get("model"),
            "rounds": round_logs,
        }
    finally:
        if cleanup and os.path.exists(workspace):
            shutil.rmtree(workspace, ignore_errors=True)



def main(
    tier=None,
    variant="lean",
    config_path=None,
    tasks_list=None,
    trials=2,
    skills=None,
    max_workers=None,
    output_dir=None,
):
    cfg = _load_config(config_path)
    _assert_live_benchmark_config(cfg)

    output_root = os.path.abspath(output_dir or tempfile.mkdtemp(prefix="mighty_mouse_"))
    logs_dir = os.path.join(output_root, "logs")
    workspaces_dir = os.path.join(output_root, "workspaces")
    os.makedirs(logs_dir, exist_ok=True)
    os.makedirs(workspaces_dir, exist_ok=True)
    print(f"[*] Results directory: {output_root}")

    tasks = []
    if tasks_list:
        tasks = [t if os.path.isabs(t) else os.path.join(TASK_DIR, t) for t in tasks_list]
    elif tier:
        eval_cfg_path = "eval/evaluation_config.json"
        if not os.path.exists(eval_cfg_path):
            print(f"Error: Config path {eval_cfg_path} not found.")
            return
        with open(eval_cfg_path, 'r') as f:
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

    # Resolve max_workers
    env_workers = os.environ.get("MIGHTY_MAX_WORKERS")
    if max_workers is not None:
        effective_max_workers = max_workers
    elif "MIGHTY_MAX_WORKERS" in os.environ:
        if not env_workers:
            print(f"Error: MIGHTY_MAX_WORKERS environment variable is empty. Must be a positive integer.")
            sys.exit(1)
        try:
            effective_max_workers = int(env_workers)
        except ValueError:
            print(f"Error: Invalid MIGHTY_MAX_WORKERS environment variable: '{env_workers}' (must be a positive integer)")
            sys.exit(1)
    else:
        effective_max_workers = MAX_WORKERS_DEFAULT

    if effective_max_workers <= 0:
        print(f"Error: max_workers must be a positive integer. Got {effective_max_workers}")
        sys.exit(1)

    print(f"[*] Dispatching {len(tasks)} tasks with max_workers={effective_max_workers} variant={variant} provider={cfg.get('provider')} model={cfg.get('model')} trials={trials}...")
    results = []
    with concurrent.futures.ProcessPoolExecutor(max_workers=effective_max_workers) as executor:
        futures = {
            executor.submit(
                run_task,
                t,
                variant,
                config_path,
                trials,
                True,
                skills,
                output_root,
            ): t
            for t in tasks
        }
        for future in concurrent.futures.as_completed(futures):
            results.append(future.result())
            time.sleep(5)  # Safe throttle

    # Summary calculations
    success_count = len([r for r in results if r.get("status") == "success" or r.get("final_status") == "success"])
    avg_latency = round(sum(r.get("latency_seconds", r.get("total_wall_clock", 0)) for r in results) / len(results), 3) if results else 0

    final_payload = {
        "summary": {
            "tier": tier or "custom",
            "variant": variant,
            "success_rate": f"{success_count}/{len(results)}",
            "max_workers": effective_max_workers,
            "avg_latency_sec": avg_latency,
            "timestamp": datetime.now().isoformat(),
        },
        "results": results,
        "output_dir": output_root,
    }

    log_filename = f"benchmark_results_{variant}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    log_path = os.path.join(logs_dir, log_filename)
    with open(log_path, "w") as f:
        json.dump(final_payload, f, indent=2)

    final_payload["report_path"] = log_path
    return final_payload
