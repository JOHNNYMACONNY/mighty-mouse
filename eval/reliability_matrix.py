"""Reliability Matrix Harness and Preflight Suite (Milestone 12).

Provides an eval-only, unconfounded matrix harness over canonical HostAdapter
and Verifier APIs with zero-generation preflight verification.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
from typing import Any, Sequence
import urllib.error
import urllib.request

import jsonschema

from eval.runner_lock import SingleInstanceLock, SingleInstanceLockError

logger = logging.getLogger(__name__)

SCHEMA_VERSION = "1.1.0"
EXPERIMENT_BASE_SHA = "06b3321b2ac0e3bb00d22484fbeb5845c138869d"
DEFAULT_CONTRACT_PATH = Path("eval/reliability_matrix_contract.json")
DEFAULT_CONFIG_PATH = Path("eval/evaluation_config.json")
DEFAULT_TASKS_DIR = Path("tasks/benchmark")
DEFAULT_MODEL = "gemma4:e4b"
DEFAULT_HOST = "http://localhost:11434"
SWARM_CONCURRENCY = 2
MAX_RECOVERY_ATTEMPTS = 1

M12_HARNESS_ALLOWED_PATHS: frozenset[str] = frozenset({
    "eval/reliability_matrix.py",
    "eval/reliability_matrix_execution.py",
    "eval/reliability_matrix_contract.json",
    "eval/test_reliability_matrix.py",
    "eval/test_reliability_matrix_execution.py",
    "eval/test_non_agent_response_application_inventory.py",
})


@dataclass(frozen=True)
class ArmDefinition:
    arm_id: str
    description: str
    execution_mode: str
    recovery_enabled: bool


ARMS: dict[str, ArmDefinition] = {
    "control_once": ArmDefinition(
        arm_id="control_once",
        description=(
            "Bare single execution "
            "(raw gemma4:e4b generation -> apply once -> verify)"
        ),
        execution_mode="bare_control",
        recovery_enabled=False,
    ),
    "mm_single": ArmDefinition(
        arm_id="mm_single",
        description="Canonical Mighty Mouse (HostAdapter.solve -> verify)",
        execution_mode="agent_solve",
        recovery_enabled=False,
    ),
    "mm_swarm": ArmDefinition(
        arm_id="mm_swarm",
        description=(
            "Canonical swarm "
            "(HostAdapter.solve_swarm concurrency=2 -> verify)"
        ),
        execution_mode="swarm_solve",
        recovery_enabled=False,
    ),
    "mm_single_recovery": ArmDefinition(
        arm_id="mm_single_recovery",
        description=(
            "Canonical + recovery "
            "(HostAdapter.solve -> verify -> max 1 agent recovery "
            "if eligible -> reverify)"
        ),
        execution_mode="agent_solve",
        recovery_enabled=True,
    ),
    "mm_swarm_recovery": ArmDefinition(
        arm_id="mm_swarm_recovery",
        description=(
            "Swarm + recovery "
            "(HostAdapter.solve_swarm concurrency=2 -> verify -> "
            "max 1 canonical agent recovery if eligible -> reverify)"
        ),
        execution_mode="swarm_solve",
        recovery_enabled=True,
    ),
}


def compute_sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def compute_sha256_file(path: Path) -> str:
    return compute_sha256_bytes(path.read_bytes())


def resolve_base_sha(repo_root: Path = Path(".")) -> str:
    """Resolve exact canonical Git commit HEAD."""
    res = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    )
    return res.stdout.strip()


def resolve_harness_sha(repo_root: Path = Path(".")) -> str:
    """Resolve exact current harness Git commit HEAD."""
    return resolve_base_sha(repo_root)


def verify_baseline_harness_delta(
    base_sha: str,
    harness_sha: str,
    repo_root: Path = Path("."),
) -> tuple[bool, list[str]]:
    """Verify that delta between base and harness is strictly in M12 allowlist.

    Fails closed if git diff command fails or if unapproved files are modified.
    Returns (True, changed_paths) if all paths approved,
    or (False, unapproved_paths) if any unapproved path is changed.
    """
    if base_sha == harness_sha:
        return (True, [])
    res = subprocess.run(
        ["git", "diff", "--name-only", f"{base_sha}..{harness_sha}"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if res.returncode != 0:
        err = res.stderr.strip() or f"exit code {res.returncode}"
        raise RuntimeError(
            f"Git diff failed between '{base_sha}' and '{harness_sha}': {err}"
        )
    changed: list[str] = []
    unapproved: list[str] = []
    for line in res.stdout.splitlines():
        trimmed = line.strip()
        if not trimmed:
            continue
        changed.append(trimmed)
        if trimmed not in M12_HARNESS_ALLOWED_PATHS:
            unapproved.append(trimmed)
    if unapproved:
        return (False, unapproved)
    return (True, changed)


def check_git_clean(repo_root: Path = Path(".")) -> tuple[bool, list[str]]:
    """Inspect worktree dirtiness excluding recognized user artifacts."""
    res = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    )
    unclean_lines: list[str] = []
    for line in res.stdout.splitlines():
        trimmed = line.strip()
        if not trimmed:
            continue
        # Preserved user-owned artifact allowed
        if "eval/prototype_apple_dashboard.html" in trimmed:
            continue
        unclean_lines.append(trimmed)
    return (len(unclean_lines) == 0, unclean_lines)


def select_deterministic_task(
    base_sha: str,
    tier_name: str,
    tasks: Sequence[str],
) -> str:
    """Deterministic selector: SHA256(sha + 'm12-pilot-v1' + tier) % count."""
    if not tasks:
        raise ValueError(f"Task list for tier '{tier_name}' cannot be empty")
    seed = f"{base_sha}m12-pilot-v1{tier_name}".encode("utf-8")
    hash_hex = hashlib.sha256(seed).hexdigest()
    idx = int(hash_hex, 16) % len(tasks)
    return tasks[idx]


def get_baseline_tracked_tasks(
    base_sha: str,
    tasks_dir: Path,
    repo_root: Path = Path("."),
) -> set[str]:
    """Retrieve set of task filenames tracked in Git tree at base_sha.

    Fails closed if git command fails.
    """
    res = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", base_sha, str(tasks_dir)],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if res.returncode != 0:
        err = res.stderr.strip() or f"exit code {res.returncode}"
        raise RuntimeError(
            f"Git tree lookup failed for '{base_sha}': {err}"
        )
    return {
        Path(line).name for line in res.stdout.splitlines() if line.strip()
    }


def evaluate_tier_corpus(
    config_path: Path = DEFAULT_CONFIG_PATH,
    tasks_dir: Path = DEFAULT_TASKS_DIR,
    base_sha: str | None = None,
    check_git_tracking: bool = True,
) -> list[dict[str, Any]]:
    """Dynamically audit configured tiers, disk files, and git tracking."""
    if not config_path.is_file():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    tiers_cfg = cfg.get("tiers", {})

    sha = base_sha or resolve_base_sha()
    tracked_tasks: set[str] | None = None
    git_lookup_error: str | None = None
    if check_git_tracking and sha:
        try:
            tracked_tasks = get_baseline_tracked_tasks(sha, tasks_dir)
        except Exception as exc:
            git_lookup_error = str(exc)

    results: list[dict[str, Any]] = []

    for name, tasks in tiers_cfg.items():
        is_rollup = (tasks == "all")
        if is_rollup:
            results.append({
                "name": name,
                "is_rollup": True,
                "total_configured": 0,
                "available_tasks": 0,
                "missing_tasks": [],
                "blocked": False,
                "sample_task": None,
            })
            continue

        if not isinstance(tasks, list):
            bad_type = type(tasks).__name__
            results.append({
                "name": name,
                "is_rollup": False,
                "total_configured": 0,
                "available_tasks": 0,
                "missing_tasks": [f"invalid_tier_config_{bad_type}"],
                "blocked": True,
                "sample_task": None,
            })
            continue

        if git_lookup_error is not None:
            # Fail closed on git provenance lookup error
            results.append({
                "name": name,
                "is_rollup": False,
                "total_configured": len(tasks),
                "available_tasks": 0,
                "missing_tasks": [
                    f"git_provenance_error: {git_lookup_error}"
                ],
                "blocked": True,
                "sample_task": None,
            })
            continue

        missing = []
        for t in tasks:
            exists_on_disk = (tasks_dir / t).is_file()
            in_baseline = (
                tracked_tasks is None or t in tracked_tasks
            )
            if not exists_on_disk or not in_baseline:
                missing.append(t)

        available = len(tasks) - len(missing)
        is_blocked = len(missing) > 0
        sample = None
        if not is_blocked and tasks:
            sample = select_deterministic_task(sha, name, tasks)

        results.append({
            "name": name,
            "is_rollup": False,
            "total_configured": len(tasks),
            "available_tasks": available,
            "missing_tasks": missing,
            "blocked": is_blocked,
            "sample_task": sample,
        })

    return results


def check_ollama_provenance(
    host: str = DEFAULT_HOST,
    model: str = DEFAULT_MODEL,
    timeout_sec: int = 5,
) -> dict[str, Any]:
    """Retrieve version and immutable model digest from Ollama."""
    server_info: dict[str, Any] = {
        "host": host,
        "available": False,
        "version": "unknown",
        "model": model,
        "model_digest": "unknown",
    }
    base_url = host.rstrip("/")
    try:
        from mighty_mouse.host.adapter import HostAdapter
        server_info["model_digest"] = HostAdapter.resolve_ollama_model_digest(
            model
        )
    except Exception:
        pass

    try:
        req_ver = urllib.request.Request(f"{base_url}/api/version")
        with urllib.request.urlopen(req_ver, timeout=timeout_sec) as resp:
            ver_data = json.loads(resp.read().decode("utf-8"))
            server_info["version"] = ver_data.get("version", "unknown")

        req_tags = urllib.request.Request(f"{base_url}/api/tags")
        with urllib.request.urlopen(req_tags, timeout=timeout_sec) as resp:
            tags_data = json.loads(resp.read().decode("utf-8"))
            models = tags_data.get("models", [])
            selected = next(
                (m for m in models if m.get("name") == model),
                None,
            )
            if selected:
                if server_info["model_digest"] == "unknown":
                    server_info["model_digest"] = selected.get(
                        "digest", "unknown"
                    )
                server_info["available"] = True
            else:
                server_info["error"] = (
                    f"Model '{model}' not found in Ollama tags"
                )
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
        server_info["error"] = f"{type(exc).__name__}: {exc}"

    return server_info


def verify_runtime_context_readiness(
    model_digest: str,
    model: str = DEFAULT_MODEL,
    workspace: Path | None = None,
) -> tuple[bool, str | None]:
    """Zero-generation readiness check using resolve_adapter_context."""
    try:
        from mighty_mouse.host.adapter import (
            HostAdapter,
            MCP_TOOL_CONTRACT_VERSION,
        )
        from mighty_mouse_mcp.server import _get_mcp_tool_signatures

        sigs = _get_mcp_tool_signatures()
        temp_ws = workspace or Path(tempfile.mkdtemp(prefix="mm_readiness_"))
        state_dir = temp_ws / ".mighty-mouse"
        state_dir.mkdir(parents=True, exist_ok=True)
        cfg = HostAdapter.build_adapter_config(
            repository="JOHNNYMACONNY/mighty-mouse",
            model_digest=model_digest,
            model_class="local-small",
            effective_context_limit=8192,
            runtime_kind="cline",
            runtime_version="3.54.0",
            ollama_model=model,
            tool_signatures=sigs,
            contract_version=MCP_TOOL_CONTRACT_VERSION,
        )
        (state_dir / "mcp-adapter.json").write_text(
            json.dumps(cfg, indent=2), encoding="utf-8"
        )
        ctx = HostAdapter.resolve_adapter_context(
            str(temp_ws),
            str(state_dir),
            tool_signatures=sigs,
            contract_version=MCP_TOOL_CONTRACT_VERSION,
        )
        if ctx.model_identity.artifact_digest != model_digest:
            return False, (
                f"Digest mismatch: {ctx.model_identity.artifact_digest} "
                f"!= {model_digest}"
            )
        return True, None
    except Exception as exc:
        return False, str(exc)


class UsageInstrumentation:
    """Thread-safe usage instrumentation for Ollama generation calls."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.generation_calls: int = 0
        self.events: list[dict[str, Any]] = []
        self.token_coverage_complete: bool = True
        self.active_phase: str = "primary"

    def set_phase(self, phase: str) -> None:
        with self._lock:
            self.active_phase = phase

    def wrap_ollama_client(self, client: Any) -> Any:
        original_generate = client.generate_content

        def instrumented_generate(sys_instr: str, user_prompt: str) -> str:
            res = original_generate(sys_instr, user_prompt)
            with self._lock:
                self.generation_calls += 1
                meta = getattr(client, "last_metadata", {})
                usage = meta.get("usage", {})
                p_tok = usage.get("prompt_tokens")
                c_tok = usage.get("completion_tokens")
                tot_tok = usage.get("total_tokens")
                if p_tok is None or c_tok is None:
                    self.token_coverage_complete = False

                p_val = int(p_tok or 0)
                c_val = int(c_tok or 0)
                t_val = int(tot_tok or (p_val + c_val))

                lat = float(meta.get("latency_seconds", 0.0))
                cfg = getattr(client, "config", {})
                event = {
                    "call_index": self.generation_calls,
                    "phase": self.active_phase,
                    "model": getattr(client, "model_name", "unknown"),
                    "provider": "ollama",
                    "temperature": cfg.get("temperature", 0.2),
                    "max_tokens": cfg.get("max_tokens", 4000),
                    "prompt_tokens": p_val,
                    "completion_tokens": c_val,
                    "total_tokens": t_val,
                    "latency_seconds": round(lat, 4),
                    "thread_id": threading.get_ident(),
                }
                self.events.append(event)
            return res

        client.generate_content = instrumented_generate
        return client


def load_contract_schema(
    contract_path: Path = DEFAULT_CONTRACT_PATH,
) -> dict[str, Any]:
    if not contract_path.is_file():
        raise FileNotFoundError(f"Contract file not found: {contract_path}")
    schema = json.loads(contract_path.read_text(encoding="utf-8"))
    jsonschema.Draft7Validator.check_schema(schema)
    return schema


def validate_payload_against_schema(
    payload: dict[str, Any],
    definition_name: str,
    contract_path: Path = DEFAULT_CONTRACT_PATH,
) -> None:
    schema = load_contract_schema(contract_path)
    definitions = schema.get("definitions", {})
    if definition_name not in definitions:
        raise ValueError(
            f"Definition '{definition_name}' not found in schema contract"
        )
    target_schema = definitions[definition_name]
    validator = jsonschema.Draft7Validator(target_schema)
    validator.validate(payload)


def run_preflight(
    experiment_id: str = "m12-pilot-preflight",
    base_sha: str | None = None,
    harness_sha: str | None = None,
    config_path: Path = DEFAULT_CONFIG_PATH,
    tasks_dir: Path = DEFAULT_TASKS_DIR,
    contract_path: Path = DEFAULT_CONTRACT_PATH,
    output_dir: Path | None = None,
    ollama_host: str = DEFAULT_HOST,
    ollama_model: str = DEFAULT_MODEL,
    lock_path: Path | None = None,
    check_git_tracking: bool = True,
    required_tiers: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Execute zero-generation dry-run checks under SingleInstanceLock."""
    out_path = output_dir or Path(f"eval/results/m12/{experiment_id}")
    lock = SingleInstanceLock(lock_path) if lock_path else SingleInstanceLock()

    with lock:
        target_harness = harness_sha or resolve_harness_sha()
        target_base = base_sha or EXPERIMENT_BASE_SHA

        is_clean, unclean_items = check_git_clean()
        config_hash = compute_sha256_file(config_path)

        schema = load_contract_schema(contract_path)
        schema_valid = isinstance(schema, dict) and "definitions" in schema

        tiers = evaluate_tier_corpus(
            config_path, tasks_dir, target_base, check_git_tracking
        )
        server_info = check_ollama_provenance(ollama_host, ollama_model)

        out_path.mkdir(parents=True, exist_ok=True)
        is_writable = os.access(out_path, os.W_OK)

        arms_list = [
            {
                "arm_id": arm.arm_id,
                "description": arm.description,
                "execution_mode": arm.execution_mode,
                "recovery_enabled": arm.recovery_enabled,
            }
            for arm in ARMS.values()
        ]

        blocking_reasons: list[str] = []
        if not is_clean:
            blocking_reasons.append(
                f"Worktree contains unapproved dirty files: {unclean_items}"
            )
        if not schema_valid:
            blocking_reasons.append("Schema contract validation failed")
        if not server_info.get("available", False):
            blocking_reasons.append(
                f"Ollama server unavailable at {ollama_host}: "
                f"{server_info.get('error', 'unknown error')}"
            )
        if server_info.get("model_digest") in ("unknown", "", None):
            blocking_reasons.append(
                f"Model digest for '{ollama_model}' could not be resolved"
            )

        changed_paths: list[str] = []
        try:
            delta_ok, changed_or_unapproved = verify_baseline_harness_delta(
                target_base, target_harness
            )
            if not delta_ok:
                blocking_reasons.append(
                    "Unapproved delta outside M12 harness allowlist: "
                    f"{changed_or_unapproved}"
                )
            else:
                changed_paths = changed_or_unapproved
        except Exception as exc:
            blocking_reasons.append(f"Provenance verification error: {exc}")

        if (
            server_info.get("available", False)
            and server_info.get("model_digest") not in ("unknown", "", None)
        ):
            ready_ok, ready_err = verify_runtime_context_readiness(
                server_info["model_digest"], ollama_model
            )
            if not ready_ok:
                blocking_reasons.append(
                    f"Runtime context readiness check failed: {ready_err}"
                )

        if required_tiers is not None:
            scoped_set = set(required_tiers)
            blocked_tiers = [
                t["name"]
                for t in tiers
                if (
                    not t["is_rollup"]
                    and t["name"] in scoped_set
                    and t["blocked"]
                )
            ]
            missing_configured_tiers = [
                name for name in required_tiers
                if not any(t["name"] == name for t in tiers)
            ]
            if missing_configured_tiers:
                missing_str = ", ".join(missing_configured_tiers)
                blocking_reasons.append(
                    f"Required tiers not found in config: {missing_str}"
                )
        else:
            blocked_tiers = [
                t["name"] for t in tiers if not t["is_rollup"] and t["blocked"]
            ]
        if blocked_tiers:
            blocking_reasons.append(
                f"Configured tiers blocked or missing from baseline: "
                f"{', '.join(blocked_tiers)}"
            )

        if not (is_writable and out_path.is_dir()):
            blocking_reasons.append(
                f"Output directory '{out_path}' is not ready/writable"
            )

        preflight_passed = (len(blocking_reasons) == 0)

        report = {
            "schema_version": SCHEMA_VERSION,
            "experiment_id": experiment_id,
            "experiment_base_sha": target_base,
            "base_sha": target_base,
            "harness_sha": target_harness,
            "baseline_to_harness_changed_paths": changed_paths,
            "git_clean": is_clean,
            "runner_lock_acquired": True,
            "schema_valid": schema_valid,
            "config_path": str(config_path),
            "config_sha256": config_hash,
            "ollama_server": server_info,
            "tiers": tiers,
            "required_tiers": (
                list(required_tiers) if required_tiers is not None else None
            ),
            "arms": arms_list,
            "output_dir": {
                "path": str(out_path),
                "writable": is_writable,
                "ready": is_writable and out_path.is_dir(),
            },
            "recovery_attempt_ceiling": MAX_RECOVERY_ATTEMPTS,
            "dry_run": True,
            "generation_calls": 0,
            "preflight_passed": preflight_passed,
            "blocking_reasons": blocking_reasons,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        validate_payload_against_schema(
            report, "preflight_report", contract_path
        )

        report_file = out_path / "preflight_report.json"
        report_file.write_text(json.dumps(report, indent=2), encoding="utf-8")

        return report


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Mighty Mouse Reliability Matrix Harness & Preflight Suite"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Perform zero-generation preflight verification (default: True)",
    )
    parser.add_argument(
        "--experiment-id",
        type=str,
        default="m12-pilot-v1",
        help="Experiment run identifier",
    )
    parser.add_argument(
        "--base-sha",
        type=str,
        default=EXPERIMENT_BASE_SHA,
        help="Assert expected experiment baseline commit SHA",
    )
    parser.add_argument(
        "--harness-sha",
        type=str,
        default=None,
        help="Assert expected harness commit SHA (default: current HEAD)",
    )
    parser.add_argument(
        "--tiers",
        nargs="*",
        default=None,
        help="Optional required tier subset (e.g. tier_1 tier_5 tier_7)",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help="Path to evaluation config JSON",
    )
    parser.add_argument(
        "--tasks-dir",
        type=Path,
        default=DEFAULT_TASKS_DIR,
        help="Directory containing benchmark task JSON files",
    )
    parser.add_argument(
        "--contract",
        type=Path,
        default=DEFAULT_CONTRACT_PATH,
        help="Path to reliability matrix contract JSON schema",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Destination directory for trial results and preflight report",
    )
    parser.add_argument(
        "--host",
        type=str,
        default=DEFAULT_HOST,
        help="Ollama host URL",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=DEFAULT_MODEL,
        help="Ollama model identifier",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    try:
        report = run_preflight(
            experiment_id=args.experiment_id,
            base_sha=args.base_sha,
            harness_sha=args.harness_sha,
            config_path=args.config,
            tasks_dir=args.tasks_dir,
            contract_path=args.contract,
            output_dir=args.output_dir,
            ollama_host=args.host,
            ollama_model=args.model,
            required_tiers=args.tiers,
        )
        passed = report["preflight_passed"]
        status_word = "PASS" if passed else "BLOCKED / FAIL"
        print("=" * 70)
        print(f"MIGHTY MOUSE RELIABILITY MATRIX PREFLIGHT: {status_word}")
        print(f"Experiment ID:   {report['experiment_id']}")
        print(f"Base SHA:        {report['base_sha']}")
        print(f"Harness SHA:     {report['harness_sha']}")
        print(f"Git Clean:       {report['git_clean']}")
        print("Runner Lock:     ACQUIRED (eval/runner_lock)")
        print(f"Schema Contract: VALID ({report['schema_version']})")
        print(f"Config SHA-256:  {report['config_sha256'][:16]}...")
        server = report["ollama_server"]
        print(f"Ollama Server:   {server['host']} (v{server['version']})")
        print(f"Model Digest:    {server['model_digest'][:16]}...")
        print(f"Recovery Ceiling:{report['recovery_attempt_ceiling']} attempt")
        print(f"Dry Run Calls:   {report['generation_calls']} calls")
        print(f"Preflight Status:{'PASSED' if passed else 'BLOCKED'}")
        if report["blocking_reasons"]:
            print("Blocking Reasons:")
            for reason in report["blocking_reasons"]:
                print(f"  [!] {reason}")
        print("-" * 70)
        print("Tiers Corpus Status:")
        for t in report["tiers"]:
            if t["is_rollup"]:
                print(f"  - {t['name']}: ROLLUP (all)")
            elif t["blocked"]:
                missing_cnt = len(t["missing_tasks"])
                print(
                    f"  - {t['name']}: BLOCKED ({missing_cnt} missing: "
                    f"{t['missing_tasks'][:2]})"
                )
            else:
                print(
                    f"  - {t['name']}: READY ({t['available_tasks']}/"
                    f"{t['total_configured']} tasks, "
                    f"sample: {t['sample_task']})"
                )
        print("=" * 70)
        return 0 if passed else 1
    except SingleInstanceLockError as exc:
        print(
            f"[!] Preflight failed: Lock contention - {exc}",
            file=sys.stderr,
        )
        return 1
    except Exception as exc:
        print(f"[!] Preflight failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
