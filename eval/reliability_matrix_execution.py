"""Reliability Matrix Trial Executor & P1 Plan Materialization (Milestone 12).

Provides the real five-arm execution engine over canonical HostAdapter,
execute_recovery_attempt, and Verifier seams with deterministic P1 plan
materialization, provenance separation, and class-level Ollama usage capture.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import logging
from pathlib import Path
import threading
import time
from typing import Any, Sequence
import urllib.error
import urllib.request

from eval.reliability_matrix import (
    ARMS,
    DEFAULT_CONFIG_PATH,
    DEFAULT_CONTRACT_PATH,
    DEFAULT_HOST,
    DEFAULT_MODEL,
    DEFAULT_TASKS_DIR,
    EXPERIMENT_BASE_SHA,
    MAX_RECOVERY_ATTEMPTS,
    SCHEMA_VERSION,
    SWARM_CONCURRENCY,
    check_ollama_provenance,
    compute_sha256_bytes,
    compute_sha256_file,
    resolve_harness_sha,
    select_deterministic_task,
    validate_payload_against_schema,
    verify_baseline_harness_delta,
)
from eval.runner_lock import SingleInstanceLock
from mighty_mouse.host.adapter import (
    HostAdapter,
    MCP_TOOL_CONTRACT_VERSION,
)
from mighty_mouse.host.hooks import (
    HostHookAction,
    HostHookEvent,
    HookVerificationSummary,
    ResolvedHostHookEvent,
)
from mighty_mouse.host.recovery import evaluate_recovery_gate
from mighty_mouse.host.recovery_execution import (
    RecoveryExecutionRequest,
    execute_recovery_attempt,
)
from mighty_mouse.orchestrator.response_application import (
    ResponseApplicationPolicy,
    ResponseApplicationRequest,
    apply_response,
)
from mighty_mouse.services.verifiers.run_benchmark import verify_task

logger = logging.getLogger(__name__)

ARM_ORDER_SEED_PREFIX = "m12-arm-order-v1"
P1_TIERS = ("tier_1", "tier_5", "tier_7")

DEFAULT_TOOL_SIGNATURES: dict[str, Any] = {
    "verify": lambda workspace: None,
}

BARE_PROMPT_TEMPLATE = """You are completing a coding task.

Title: {title}
Task: {description}
Constraints: {constraints}
Required files: {expected_files}

Write the complete implementation. Return each required file as one fenced
block whose opening fence is exactly ```language:path. Do not omit the path.
"""


def build_bare_prompt(task: dict[str, Any]) -> str:
    return BARE_PROMPT_TEMPLATE.format(
        title=task.get("title", task.get("id", "task")),
        description=task.get("description", ""),
        constraints=json.dumps(task.get("constraints", {}), sort_keys=True),
        expected_files=", ".join(task.get("expected_files", [])),
    )


class CaptureOllamaUsage:
    """Thread-safe manager wrapping OllamaClient.generate_content."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.events: list[dict[str, Any]] = []
        self.generation_calls: int = 0
        self.token_coverage_complete: bool = True
        self.active_phase: str = "primary"
        self._original_generate: Any = None

    def set_phase(self, phase: str) -> None:
        with self._lock:
            self.active_phase = phase

    def record_generation(
        self,
        *,
        phase: str | None = None,
        model: str = "unknown",
        provider: str = "ollama",
        temperature: float = 0.2,
        max_tokens: int = 4000,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        total_tokens: int | None = None,
        latency_seconds: float = 0.0,
        thread_id: int | None = None,
        thread_name: str | None = None,
    ) -> None:
        with self._lock:
            self.generation_calls += 1
            if prompt_tokens is None or completion_tokens is None:
                self.token_coverage_complete = False

            p_val = int(prompt_tokens or 0)
            c_val = int(completion_tokens or 0)
            t_val = int(
                total_tokens if total_tokens is not None else (p_val + c_val)
            )

            event = {
                "call_index": self.generation_calls,
                "phase": phase or self.active_phase,
                "model": model,
                "provider": provider,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "prompt_tokens": p_val,
                "completion_tokens": c_val,
                "total_tokens": t_val,
                "latency_seconds": round(float(latency_seconds), 4),
                "thread_id": (
                    thread_id if thread_id is not None
                    else threading.get_ident()
                ),
                "thread_name": (
                    thread_name if thread_name is not None
                    else threading.current_thread().name
                ),
            }
            self.events.append(event)

    def __enter__(self) -> CaptureOllamaUsage:
        try:
            from mighty_mouse.orchestrator.ollama_client import OllamaClient
        except ImportError:
            from ollama_client import OllamaClient  # type: ignore[no-redef]

        self._original_generate = OllamaClient.generate_content
        capture = self

        def wrapped_generate(
            client_self: Any, sys_instr: str, user_prompt: str
        ) -> str:
            res = capture._original_generate(
                client_self, sys_instr, user_prompt
            )
            meta = getattr(client_self, "last_metadata", {})
            usage = meta.get("usage", {})
            cfg = getattr(client_self, "config", {})
            capture.record_generation(
                phase=capture.active_phase,
                model=getattr(client_self, "model_name", "unknown"),
                provider="ollama",
                temperature=cfg.get("temperature", 0.2),
                max_tokens=cfg.get("max_tokens", 4000),
                prompt_tokens=usage.get("prompt_tokens"),
                completion_tokens=usage.get("completion_tokens"),
                total_tokens=usage.get("total_tokens"),
                latency_seconds=float(meta.get("latency_seconds", 0.0)),
                thread_id=threading.get_ident(),
                thread_name=threading.current_thread().name,
            )
            return res

        OllamaClient.generate_content = wrapped_generate
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        try:
            from mighty_mouse.orchestrator.ollama_client import OllamaClient
            if self._original_generate is not None:
                OllamaClient.generate_content = self._original_generate
        except Exception:
            pass
        finally:
            self._original_generate = None


def request_control_generation(
    prompt: str,
    model: str,
    host: str,
    timeout_sec: int,
) -> tuple[str, dict[str, Any]]:
    """Execute bare-control Ollama generation preserving raw token metadata."""
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.2,
            "num_predict": 4000,
            "num_ctx": 32768,
        },
    }
    req = urllib.request.Request(
        host.rstrip("/") + "/api/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    started = time.monotonic()
    with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    prompt_tok = body.get("prompt_eval_count")
    comp_tok = body.get("eval_count")
    tot_tok = None
    if prompt_tok is not None and comp_tok is not None:
        tot_tok = int(prompt_tok) + int(comp_tok)
    metadata: dict[str, Any] = {
        "latency_seconds": round(time.monotonic() - started, 4),
        "prompt_tokens": prompt_tok,
        "completion_tokens": comp_tok,
        "total_tokens": tot_tok,
    }
    return body.get("response", ""), metadata


def deterministic_arm_order(
    base_sha: str,
    task_id: str,
    replicate: int,
    arms: Sequence[str] | None = None,
) -> list[str]:
    """Sort arms deterministically using SHA256 arm ordering hash."""
    arm_list = list(arms) if arms is not None else list(ARMS.keys())

    def _arm_key(arm_id: str) -> str:
        seed = f"{base_sha}{ARM_ORDER_SEED_PREFIX}{task_id}{replicate}{arm_id}"
        return hashlib.sha256(seed.encode("utf-8")).hexdigest()

    return sorted(arm_list, key=_arm_key)


@dataclass(frozen=True)
class TrialPlanUnit:
    order_index: int
    trial_order_index: int
    trial_id: str
    tier: str
    task_id: str
    task_file: str
    arm: str
    replicate: int
    experiment_base_sha: str
    harness_sha: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "order_index": self.order_index,
            "trial_order_index": self.trial_order_index,
            "trial_id": self.trial_id,
            "tier": self.tier,
            "task_id": self.task_id,
            "task_file": self.task_file,
            "arm": self.arm,
            "replicate": self.replicate,
            "experiment_base_sha": self.experiment_base_sha,
            "harness_sha": self.harness_sha,
        }


def materialize_p1_plan(
    experiment_id: str = "m12-pilot-01",
    base_sha: str = EXPERIMENT_BASE_SHA,
    harness_sha: str | None = None,
    config_path: Path = DEFAULT_CONFIG_PATH,
    tasks_dir: Path = DEFAULT_TASKS_DIR,
    contract_path: Path = DEFAULT_CONTRACT_PATH,
    output_dir: Path | None = None,
    replicates: int = 1,
    tiers: Sequence[str] = P1_TIERS,
) -> dict[str, Any]:
    """Deterministically materialize zero-generation P1 execution plan.

    For each tier in `tiers`, selects the canonical task via
    select_deterministic_task, determines the arm order via
    deterministic_arm_order, and assembles the sequence of trial units.
    Selection always uses base_sha (defaulting to EXPERIMENT_BASE_SHA).
    """
    if not config_path.is_file():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    tiers_cfg = cfg.get("tiers", {})

    target_harness = harness_sha or resolve_harness_sha()
    trial_units: list[dict[str, Any]] = []
    order_index = 0

    for tier in tiers:
        if tier not in tiers_cfg:
            raise ValueError(f"Tier '{tier}' not configured in {config_path}")
        tier_tasks = tiers_cfg[tier]
        if not isinstance(tier_tasks, list) or not tier_tasks:
            raise ValueError(f"Tier '{tier}' has invalid or empty tasks list")

        selected_file = select_deterministic_task(base_sha, tier, tier_tasks)
        task_json_path = tasks_dir / selected_file
        if not task_json_path.is_file():
            raise FileNotFoundError(
                f"Selected task file not found on disk: {task_json_path}"
            )
        task_data = json.loads(task_json_path.read_text(encoding="utf-8"))
        task_id = str(task_data.get("id", Path(selected_file).stem))

        for rep in range(1, replicates + 1):
            ordered_arms = deterministic_arm_order(base_sha, task_id, rep)
            for arm_name in ordered_arms:
                trial_id = f"trial_{tier}_{task_id}_{arm_name}_rep{rep}"
                unit = TrialPlanUnit(
                    order_index=order_index,
                    trial_order_index=order_index,
                    trial_id=trial_id,
                    tier=tier,
                    task_id=task_id,
                    task_file=selected_file,
                    arm=arm_name,
                    replicate=rep,
                    experiment_base_sha=base_sha,
                    harness_sha=target_harness,
                )
                trial_units.append(unit.to_dict())
                order_index += 1

    plan: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "experiment_id": experiment_id,
        "experiment_base_sha": base_sha,
        "base_sha": base_sha,
        "harness_sha": target_harness,
        "replicates": replicates,
        "tiers": list(tiers),
        "trial_units": trial_units,
        "arm_order_seed": ARM_ORDER_SEED_PREFIX,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    validate_payload_against_schema(plan, "execution_plan", contract_path)

    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)
        plan_file = output_dir / "execution_plan.json"
        plan_file.write_text(json.dumps(plan, indent=2), encoding="utf-8")

    return plan


def classify_failure(
    verify_result: dict[str, Any] | None,
    *,
    exception: Exception | None = None,
    is_recovery: bool = False,
) -> str | None:
    """Classify verification or execution outcome into closed vocabulary."""
    if exception is not None:
        exc_str = str(exception).lower()
        if isinstance(exception, TimeoutError) or "timeout" in exc_str:
            return "timeout"
        if "generate" in exc_str or "ollama" in exc_str:
            return "generation_error"
        return "application_error"

    if verify_result is None:
        return "verifier_error"

    if verify_result.get("status") == "success":
        return None

    if is_recovery:
        return "recovery_failed"

    if verify_result.get("scope") == "FAIL":
        return "scope_failure"
    if verify_result.get("adherence") == "FAIL":
        return "adherence_failure"
    return "test_failure"


def setup_trial_workspace(
    workspace: Path,
    task_config: dict[str, Any],
    ollama_model: str,
    ollama_host: str,
    model_digest: str,
    tool_signatures: dict[str, Any],
    arm_name: str,
) -> tuple[Path, Path]:
    """Create isolated workspace, task file, p_cfg, and adapter config."""
    workspace.mkdir(parents=True, exist_ok=True)

    task_file = workspace / "task.json"
    task_file.write_text(json.dumps(task_config, indent=2), encoding="utf-8")

    p_cfg_path = workspace / "model_config.yaml"
    p_cfg_content = (
        f"model: {ollama_model}\n"
        f"provider: ollama\n"
        f"ollama_host: {ollama_host}\n"
        f"temperature: 0.2\n"
        f"max_tokens: 4000\n"
        f"prompt_segments: []\n"
        f"system_prompt_path: ''\n"
    )
    p_cfg_path.write_text(p_cfg_content, encoding="utf-8")

    state_dir = workspace / ".mighty-mouse"
    state_dir.mkdir(parents=True, exist_ok=True)

    adapter_config = HostAdapter.build_adapter_config(
        repository="JOHNNYMACONNY/mighty-mouse",
        model_digest=model_digest,
        model_class="local-small",
        effective_context_limit=8192,
        runtime_kind="cline",
        runtime_version="3.54.0",
        ollama_model=ollama_model if arm_name != "control_once" else None,
        tool_signatures=tool_signatures,
        contract_version=MCP_TOOL_CONTRACT_VERSION,
    )
    (state_dir / "mcp-adapter.json").write_text(
        json.dumps(adapter_config, indent=2), encoding="utf-8"
    )

    return task_file, p_cfg_path


def execute_trial_unit(
    plan_unit: dict[str, Any],
    *,
    experiment_id: str,
    base_sha: str = EXPERIMENT_BASE_SHA,
    harness_sha: str | None = None,
    workspace_root: Path,
    tasks_dir: Path = DEFAULT_TASKS_DIR,
    contract_path: Path = DEFAULT_CONTRACT_PATH,
    output_dir: Path | None = None,
    ollama_host: str = DEFAULT_HOST,
    ollama_model: str = DEFAULT_MODEL,
    tool_signatures: dict[str, Any] | None = None,
    provenance_info: dict[str, Any] | None = None,
    timeout_sec: int = 120,
    usage_capture: CaptureOllamaUsage | None = None,
) -> dict[str, Any]:
    """Execute a single trial unit across one of the five arms."""
    target_harness = harness_sha or resolve_harness_sha()
    sigs = tool_signatures or DEFAULT_TOOL_SIGNATURES
    arm = plan_unit["arm"]
    if arm not in ARMS:
        raise ValueError(f"Unknown arm '{arm}' in plan unit")

    arm_def = ARMS[arm]
    task_file_name = plan_unit["task_file"]
    task_json_path = tasks_dir / task_file_name
    if not task_json_path.is_file():
        raise FileNotFoundError(f"Task file not found: {task_json_path}")

    task_bytes = task_json_path.read_bytes()
    task_sha256 = compute_sha256_bytes(task_bytes)
    task_config = json.loads(task_bytes.decode("utf-8"))

    server_info = provenance_info or check_ollama_provenance(
        ollama_host, ollama_model
    )
    model_digest = server_info.get("model_digest") or ("sha256:" + "0" * 64)

    trial_id = plan_unit["trial_id"]
    trial_workspace = workspace_root / trial_id
    iso_workspace = workspace_root / f"{trial_id}_verify"

    task_file, p_cfg_file = setup_trial_workspace(
        trial_workspace,
        task_config,
        ollama_model,
        ollama_host,
        model_digest,
        sigs,
        arm,
    )
    if arm in ("mm_swarm", "mm_swarm_recovery"):
        iso_workspace.mkdir(parents=True, exist_ok=True)

    adapter = HostAdapter()
    profile, tool_contract_digest, prompt_template_digest = (
        HostAdapter.build_execution_profile(
            runtime_kind="cline",
            runtime_version="3.54.0",
            effective_context_limit=8192,
            tool_signatures=sigs,
            contract_version=MCP_TOOL_CONTRACT_VERSION,
        )
    )

    primary_exception: Exception | None = None
    first_verif: dict[str, Any] | None = None
    terminal_verif: dict[str, Any] | None = None
    recovery_eligible = False
    recovery_gate_reason: str | None = None
    recovery_attempted = False
    recovery_completed = False
    terminal_failure_cat: str | None = None

    active_capture = usage_capture or CaptureOllamaUsage()
    ctx_mgr = active_capture if usage_capture is None else None

    wall_start = time.monotonic()
    try:
        if ctx_mgr is not None:
            ctx_mgr.__enter__()

        active_capture.set_phase("primary")

        # 1. Primary Execution
        if arm == "control_once":
            try:
                prompt = build_bare_prompt(task_config)
                raw_response, meta = request_control_generation(
                    prompt, ollama_model, ollama_host, timeout_sec
                )
                active_capture.record_generation(
                    phase="primary",
                    model=ollama_model,
                    prompt_tokens=meta.get("prompt_tokens"),
                    completion_tokens=meta.get("completion_tokens"),
                    total_tokens=meta.get("total_tokens"),
                    latency_seconds=float(meta.get("latency_seconds", 0.0)),
                )
                apply_response(
                    ResponseApplicationRequest(
                        raw_response=raw_response,
                        policy=ResponseApplicationPolicy(
                            workspace_root=str(trial_workspace),
                        ),
                    )
                )
            except Exception as exc:
                primary_exception = exc

        elif arm in ("mm_single", "mm_single_recovery"):
            try:
                adapter.solve(
                    workspace=str(trial_workspace),
                    p_cfg_path=str(p_cfg_file),
                    task_input=str(task_file),
                    tool_signatures=sigs,
                )
            except Exception as exc:
                primary_exception = exc

        elif arm in ("mm_swarm", "mm_swarm_recovery"):
            try:
                adapter.solve_swarm(
                    workspace=str(trial_workspace),
                    task_input=json.dumps(task_config),
                    verification_workspace=str(iso_workspace),
                    concurrency=SWARM_CONCURRENCY,
                    tool_signatures=sigs,
                    task_config=task_config,
                    timeout_sec=timeout_sec,
                )
            except Exception as exc:
                primary_exception = exc

        # 2. Authoritative First Verification
        if primary_exception is None:
            try:
                first_verif = verify_task(
                    task_config, workspace=str(trial_workspace)
                )
            except Exception as exc:
                first_verif = {
                    "status": "fail",
                    "reason": f"Verifier crash: {exc}",
                }

        first_passed = (
            first_verif is not None and first_verif.get("status") == "success"
        )
        first_failure_cat = (
            None if first_passed
            else classify_failure(first_verif, exception=primary_exception)
        )

        terminal_passed = first_passed
        terminal_verif = first_verif
        terminal_failure_cat = first_failure_cat

        # 3. Recovery Handling (only for eligible arms on primary failure)
        if arm_def.recovery_enabled and not first_passed:
            expected_files = tuple(task_config.get("expected_files", []))
            recovery_action = HostHookAction(
                kind="file_write",
                mutation_class="workspace_mutation",
                target_paths=expected_files,
            )
            recovery_event = HostHookEvent(
                schema_version=1,
                event_id=f"m12-rec-{trial_id}",
                phase="post_action",
                workspace=str(trial_workspace),
                action=recovery_action,
                source="m12_reliability_matrix",
            )
            resolved_ctx = adapter.resolve_adapter_context(
                workspace=str(trial_workspace),
                tool_signatures=sigs,
            )
            resolved_event = ResolvedHostHookEvent(
                event=recovery_event,
                runtime_context=resolved_ctx,
            )
            verif_summary = HookVerificationSummary(
                occurred=True,
                passed=False,
                summary=(
                    first_verif.get("reason", "Primary verification failed")
                    if first_verif else "Primary execution failed"
                ),
            )
            decision = evaluate_recovery_gate(
                resolved_event,
                verif_summary,
                enabled=True,
                attempts_used=0,
                recovery_in_progress=False,
            )
            recovery_eligible = decision.eligible
            recovery_gate_reason = decision.gate_reason

            if decision.eligible:
                active_capture.set_phase("recovery")
                rec_request = RecoveryExecutionRequest(
                    resolved_event=resolved_event,
                    decision=decision,
                    p_cfg_path=str(p_cfg_file),
                    task_input_path=str(task_file),
                )
                attempt = execute_recovery_attempt(
                    rec_request,
                    feedback_str=verif_summary.summary,
                )
                recovery_attempted = attempt.attempted
                recovery_completed = attempt.completed

                try:
                    terminal_verif = verify_task(
                        task_config, workspace=str(trial_workspace)
                    )
                except Exception as exc:
                    terminal_verif = {
                        "status": "fail",
                        "reason": f"Reverifier crash: {exc}",
                    }

                terminal_passed = (
                    terminal_verif is not None
                    and terminal_verif.get("status") == "success"
                )
                if terminal_passed:
                    terminal_failure_cat = None
                else:
                    terminal_failure_cat = classify_failure(
                        terminal_verif, is_recovery=True
                    )

    finally:
        wall_latency = round(time.monotonic() - wall_start, 4)
        if ctx_mgr is not None:
            ctx_mgr.__exit__(None, None, None)

    # 4. Usage Aggregation
    events = active_capture.events
    primary_events = [e for e in events if e.get("phase") == "primary"]
    recovery_events = [e for e in events if e.get("phase") == "recovery"]

    p_prompt_tok = sum(e["prompt_tokens"] for e in primary_events)
    p_comp_tok = sum(e["completion_tokens"] for e in primary_events)
    r_prompt_tok = sum(e["prompt_tokens"] for e in recovery_events)
    r_comp_tok = sum(e["completion_tokens"] for e in recovery_events)
    tot_tok = p_prompt_tok + p_comp_tok + r_prompt_tok + r_comp_tok
    model_lat = round(sum(e["latency_seconds"] for e in events), 4)

    prompt_sha = (
        compute_sha256_bytes(BARE_PROMPT_TEMPLATE.encode("utf-8"))
        if arm == "control_once"
        else prompt_template_digest
    )

    p_cfg_hash = compute_sha256_file(p_cfg_file)

    delta_ok, changed_or_unapproved = verify_baseline_harness_delta(
        base_sha, target_harness
    )
    changed_paths = changed_or_unapproved if delta_ok else []

    trace_data = {
        "trial_id": trial_id,
        "arm": arm,
        "tier": plan_unit["tier"],
        "task_id": plan_unit["task_id"],
        "events": events,
        "primary_verification": first_verif,
        "terminal_verification": terminal_verif,
        "primary_exception": (
            str(primary_exception) if primary_exception else None
        ),
    }
    trace_relpath: str | None = None
    trace_sha256: str | None = None
    if output_dir is not None:
        traces_dir = output_dir / "traces"
        traces_dir.mkdir(parents=True, exist_ok=True)
        trace_file = traces_dir / f"{trial_id}.json"
        trace_bytes = json.dumps(trace_data, indent=2).encode("utf-8")
        trace_file.write_bytes(trace_bytes)
        trace_relpath = f"traces/{trial_id}.json"
        trace_sha256 = hashlib.sha256(trace_bytes).hexdigest()

    trial_order_idx = plan_unit.get(
        "trial_order_index", plan_unit.get("order_index", 0)
    )

    trial_record: dict[str, Any] = {
        "identity": {
            "schema_version": SCHEMA_VERSION,
            "experiment_id": experiment_id,
            "trial_id": trial_id,
            "trial_order_index": trial_order_idx,
            "experiment_base_sha": base_sha,
            "base_sha": base_sha,
            "harness_sha": target_harness,
            "arm": arm,
            "replicate": plan_unit["replicate"],
        },
        "task": {
            "configured_tier": plan_unit["tier"],
            "task_id": plan_unit["task_id"],
            "task_file": task_file_name,
            "task_sha256": task_sha256,
        },
        "provenance": {
            "provider": "ollama",
            "ollama_version": server_info.get("version", "unknown"),
            "model": ollama_model,
            "model_digest": model_digest,
            "agent_config_sha256": p_cfg_hash,
            "prompt_template_sha256": prompt_sha,
            "execution_profile_id": (
                "bare_baseline" if arm == "control_once"
                else profile.profile_id
            ),
            "tool_contract_digest": (
                "sha256:" + "0" * 64 if arm == "control_once"
                else tool_contract_digest
            ),
            "runtime_version": "3.54.0",
            "experiment_base_sha": base_sha,
            "harness_sha": target_harness,
            "baseline_to_harness_changed_paths": changed_paths,
        },
        "execution": {
            "swarm_concurrency": (
                SWARM_CONCURRENCY if "swarm" in arm else 1
            ),
            "internal_attempts": 1,
            "generation_calls": len(events),
            "recovery_enabled": arm_def.recovery_enabled,
            "recovery_attempt_limit": MAX_RECOVERY_ATTEMPTS,
            "recovery_attempted": recovery_attempted,
            "recovery_completed": recovery_completed,
            "recovery_trigger_source": (
                "matrix_synthesized_post_action_v1"
                if recovery_attempted
                else "none"
            ),
        },
        "verification": {
            "first_passed": first_passed,
            "first_failure_category": first_failure_cat,
            "terminal_passed": terminal_passed,
            "terminal_failure_category": terminal_failure_cat,
            "recovery_eligible": recovery_eligible,
            "recovery_gate_reason": recovery_gate_reason,
        },
        "cost": {
            "primary_prompt_tokens": p_prompt_tok,
            "primary_completion_tokens": p_comp_tok,
            "recovery_prompt_tokens": r_prompt_tok,
            "recovery_completion_tokens": r_comp_tok,
            "total_tokens": tot_tok,
            "wall_latency_seconds": wall_latency,
            "model_latency_seconds": model_lat,
        },
        "validity": {
            "provenance_complete": (
                server_info.get("available", False)
                and model_digest not in ("unknown", "", None)
            ),
            "token_coverage_complete": active_capture.token_coverage_complete,
            "verifier_completed": terminal_verif is not None,
            "infrastructure_error": (
                None if primary_exception is None else str(primary_exception)
            ),
            "trace_artifact_relpath": trace_relpath,
            "trace_artifact_sha256": trace_sha256,
        },
    }

    validate_payload_against_schema(
        trial_record, "trial_record", contract_path
    )

    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)
        rec_file = output_dir / f"{trial_id}.json"
        rec_file.write_text(
            json.dumps(trial_record, indent=2), encoding="utf-8"
        )

    return trial_record


def execute_matrix_plan(
    plan: dict[str, Any],
    *,
    workspace_root: Path,
    output_dir: Path,
    contract_path: Path = DEFAULT_CONTRACT_PATH,
    tasks_dir: Path = DEFAULT_TASKS_DIR,
    config_path: Path = DEFAULT_CONFIG_PATH,
    ollama_host: str = DEFAULT_HOST,
    ollama_model: str = DEFAULT_MODEL,
    lock_path: Path | None = None,
    dry_run: bool = False,
    tool_signatures: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute all units in an execution plan under SingleInstanceLock."""
    lock = SingleInstanceLock(lock_path) if lock_path else SingleInstanceLock()
    with lock:
        output_dir.mkdir(parents=True, exist_ok=True)
        provenance = check_ollama_provenance(ollama_host, ollama_model)

        target_base = plan.get("experiment_base_sha", plan["base_sha"])
        target_harness = plan.get("harness_sha") or resolve_harness_sha()
        delta_ok, changed_or_unapproved = verify_baseline_harness_delta(
            target_base, target_harness
        )
        changed_paths = changed_or_unapproved if delta_ok else []

        trial_records: list[dict[str, Any]] = []
        for unit in plan.get("trial_units", []):
            rec = execute_trial_unit(
                unit,
                experiment_id=plan["experiment_id"],
                base_sha=target_base,
                harness_sha=target_harness,
                workspace_root=workspace_root,
                tasks_dir=tasks_dir,
                contract_path=contract_path,
                output_dir=output_dir,
                ollama_host=ollama_host,
                ollama_model=ollama_model,
                tool_signatures=tool_signatures,
                provenance_info=provenance,
            )
            trial_records.append(rec)

        arm_counts: dict[str, dict[str, int]] = {}
        for rec in trial_records:
            arm_name = rec["identity"]["arm"]
            if arm_name not in arm_counts:
                arm_counts[arm_name] = {"total": 0, "passed": 0}
            arm_counts[arm_name]["total"] += 1
            if rec["verification"]["terminal_passed"]:
                arm_counts[arm_name]["passed"] += 1

        summary = {
            "schema_version": SCHEMA_VERSION,
            "experiment_id": plan["experiment_id"],
            "experiment_base_sha": target_base,
            "base_sha": target_base,
            "harness_sha": target_harness,
            "baseline_to_harness_changed_paths": changed_paths,
            "trial_count": len(trial_records),
            "arms": list(arm_counts.keys()),
            "metrics": {
                "arms": arm_counts,
                "total_passed": sum(
                    1 for r in trial_records
                    if r["verification"]["terminal_passed"]
                ),
                "total_tokens": sum(
                    r["cost"]["total_tokens"] for r in trial_records
                ),
            },
            "dry_run": dry_run,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        validate_payload_against_schema(
            summary, "run_summary", contract_path
        )
        summary_file = output_dir / "run_summary.json"
        summary_file.write_text(
            json.dumps(summary, indent=2), encoding="utf-8"
        )
        return summary
