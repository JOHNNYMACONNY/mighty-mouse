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
import re
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
from eval.run_bare_baseline import (
    PROMPT_TEMPLATE as BARE_PROMPT_TEMPLATE,
    build_prompt as build_bare_prompt,
)
from eval.runner_lock import SingleInstanceLock
from mighty_mouse.host.adapter import (
    AdapterRuntimeContext,
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
from mighty_mouse_mcp.server import _get_mcp_tool_signatures

logger = logging.getLogger(__name__)

ARM_ORDER_SEED_PREFIX = "m12-arm-order-v1"
P1_TIERS = ("tier_1", "tier_5", "tier_7")
CANONICAL_MODEL_CONFIG_PATH = Path("configs/mighty_mouse_v1.yaml")


class CaptureOllamaUsage:
    """Thread-safe manager wrapping OllamaClient.generate_content."""

    def __init__(
        self,
        *,
        output_dir: Path | None = None,
        trial_id: str | None = None,
    ) -> None:
        self._lock = threading.Lock()
        self.events: list[dict[str, Any]] = []
        self.generation_calls: int = 0
        self.token_coverage_complete: bool = True
        self.active_phase: str = "primary"
        self._original_generate: Any = None
        self.output_dir: Path | None = output_dir
        self.trial_id: str | None = trial_id

    def configure_trial(
        self,
        output_dir: Path | None,
        trial_id: str | None,
    ) -> None:
        with self._lock:
            self.output_dir = output_dir
            self.trial_id = trial_id

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
        raw_response_text: str | None = None,
    ) -> None:
        with self._lock:
            self.generation_calls += 1
            call_phase = phase or self.active_phase
            if prompt_tokens is None or completion_tokens is None:
                self.token_coverage_complete = False

            p_val = int(prompt_tokens) if prompt_tokens is not None else None
            c_val = (
                int(completion_tokens)
                if completion_tokens is not None
                else None
            )
            if total_tokens is not None:
                t_val = int(total_tokens)
            elif p_val is not None and c_val is not None:
                t_val = p_val + c_val
            else:
                t_val = None

            relpath: str | None = None
            sha256_val: str | None = None
            if raw_response_text is not None:
                raw_bytes = raw_response_text.encode("utf-8")
                sha256_val = hashlib.sha256(raw_bytes).hexdigest()
                if self.output_dir is not None and self.trial_id is not None:
                    raw_dir = (
                        self.output_dir / "raw_responses" / self.trial_id
                    )
                    raw_dir.mkdir(parents=True, exist_ok=True)
                    fname = (
                        f"call_{self.generation_calls:03d}_{call_phase}.txt"
                    )
                    (raw_dir / fname).write_bytes(raw_bytes)
                    relpath = f"raw_responses/{self.trial_id}/{fname}"

            event = {
                "call_index": self.generation_calls,
                "phase": call_phase,
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
                "raw_response_relpath": relpath,
                "raw_response_sha256": sha256_val,
            }
            self.events.append(event)

    @property
    def raw_response_artifacts(self) -> list[dict[str, Any]]:
        """Return canonical list of raw response artifact descriptors."""
        return [
            {
                "call_index": e["call_index"],
                "phase": e["phase"],
                "relpath": e.get("raw_response_relpath"),
                "sha256": e.get("raw_response_sha256"),
            }
            for e in self.events
        ]

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
            t0 = time.monotonic()
            try:
                res = capture._original_generate(
                    client_self, sys_instr, user_prompt
                )
                dt = time.monotonic() - t0
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
                    latency_seconds=float(meta.get("latency_seconds", dt)),
                    thread_id=threading.get_ident(),
                    thread_name=threading.current_thread().name,
                    raw_response_text=res,
                )
                return res
            except Exception:
                dt = time.monotonic() - t0
                cfg = getattr(client_self, "config", {})
                capture.record_generation(
                    phase=capture.active_phase,
                    model=getattr(client_self, "model_name", "unknown"),
                    provider="ollama",
                    temperature=cfg.get("temperature", 0.2),
                    max_tokens=cfg.get("max_tokens", 4000),
                    prompt_tokens=None,
                    completion_tokens=None,
                    total_tokens=None,
                    latency_seconds=dt,
                    thread_id=threading.get_ident(),
                    thread_name=threading.current_thread().name,
                    raw_response_text=None,
                )
                raise

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
    repo_root: Path = Path("."),
) -> dict[str, Any]:
    """Deterministically materialize zero-generation P1 execution plan.

    For each tier in `tiers`, selects the canonical task via
    select_deterministic_task, determines the arm order via
    deterministic_arm_order, and assembles the sequence of trial units.
    Selection always uses base_sha (defaulting to EXPERIMENT_BASE_SHA).
    """
    resolved_root = Path(repo_root).resolve()
    resolved_cfg = (
        config_path
        if config_path.is_absolute()
        else (resolved_root / config_path)
    )
    if not resolved_cfg.is_file():
        raise FileNotFoundError(f"Config file not found: {resolved_cfg}")
    cfg = json.loads(resolved_cfg.read_text(encoding="utf-8"))
    tiers_cfg = cfg.get("tiers", {})

    resolved_tasks_dir = (
        tasks_dir
        if tasks_dir.is_absolute()
        else (resolved_root / tasks_dir)
    )
    resolved_contract = (
        contract_path
        if contract_path.is_absolute()
        else (resolved_root / contract_path)
    )

    target_harness = harness_sha or resolve_harness_sha(
        repo_root=resolved_root
    )
    trial_units: list[dict[str, Any]] = []
    order_index = 0

    for tier in tiers:
        if tier not in tiers_cfg:
            raise ValueError(f"Tier '{tier}' not configured in {resolved_cfg}")
        tier_tasks = tiers_cfg[tier]
        if not isinstance(tier_tasks, list) or not tier_tasks:
            raise ValueError(f"Tier '{tier}' has invalid or empty tasks list")

        selected_file = select_deterministic_task(base_sha, tier, tier_tasks)
        task_json_path = resolved_tasks_dir / selected_file
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

    validate_payload_against_schema(
        plan, "execution_plan", resolved_contract
    )

    if output_dir is not None:
        resolved_out = (
            output_dir
            if output_dir.is_absolute()
            else (resolved_root / output_dir)
        )
        resolved_out.mkdir(parents=True, exist_ok=True)
        plan_file = resolved_out / "execution_plan.json"
        plan_file.write_text(json.dumps(plan, indent=2), encoding="utf-8")

    return plan


def classify_failure(
    verify_result: dict[str, Any] | None,
    *,
    exception: Exception | None = None,
    stage: str | None = None,
    is_recovery: bool = False,
) -> str | None:
    """Classify verification or execution outcome into closed vocabulary."""
    if exception is not None:
        exc_str = str(exception).lower()
        if isinstance(exception, TimeoutError) or "timeout" in exc_str:
            return "timeout"
        if (
            stage == "generation"
            or "generate" in exc_str
            or "ollama" in exc_str
        ):
            return "generation_error"
        if (
            stage == "schema"
            or "schema" in exc_str
            or "ambiguous" in exc_str
            or "no valid file" in exc_str
            or "xml leakage" in exc_str
            or "oversized" in exc_str
        ):
            return "response_schema_error"
        if (
            stage == "application"
            or "write not permitted" in exc_str
            or "deletion not permitted" in exc_str
            or "traversal" in exc_str
        ):
            return "application_error"
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


def prepare_fresh_trial_workspace(
    workspace: Path,
    isolation_workspace: Path | None = None,
    workspace_root: Path | None = None,
) -> None:
    """Enforce fresh trial workspaces; fail closed if pre-existing."""
    if workspace_root is not None:
        root_res = Path(workspace_root).resolve()
        ws_res = Path(workspace).resolve()
        try:
            ws_res.relative_to(root_res)
        except ValueError:
            raise ValueError(
                f"Workspace path '{workspace}' escapes workspace_root "
                f"'{workspace_root}'"
            )
        if ws_res == root_res:
            raise ValueError(
                f"Workspace path cannot be workspace_root: '{workspace}'"
            )

        if isolation_workspace is not None:
            iso_res = Path(isolation_workspace).resolve()
            try:
                iso_res.relative_to(root_res)
            except ValueError:
                raise ValueError(
                    f"Isolation workspace path '{isolation_workspace}' "
                    f"escapes workspace_root '{workspace_root}'"
                )
            if iso_res == root_res:
                raise ValueError(
                    "Isolation workspace cannot be workspace_root: "
                    f"'{isolation_workspace}'"
                )

    ws_exists = workspace.exists()
    iso_exists = (
        isolation_workspace.exists()
        if isolation_workspace is not None
        else False
    )
    if ws_exists or iso_exists:
        if ws_exists and iso_exists:
            msg = (
                f"Both trial workspace '{workspace}' and isolation workspace "
                f"'{isolation_workspace}' already exist."
            )
        elif ws_exists:
            msg = f"Trial workspace already exists at '{workspace}'."
        else:
            msg = (
                f"Isolation workspace exists at '{isolation_workspace}'."
            )
        raise FileExistsError(
            f"{msg} Fail closed to preserve existing experimental evidence."
        )

    workspace.mkdir(parents=True, exist_ok=False)
    if isolation_workspace is not None:
        isolation_workspace.mkdir(parents=True, exist_ok=False)


def validate_execution_plan(
    plan: dict[str, Any],
    *,
    contract_path: Path = DEFAULT_CONTRACT_PATH,
    config_path: Path = DEFAULT_CONFIG_PATH,
    tasks_dir: Path = DEFAULT_TASKS_DIR,
    repo_root: Path = Path("."),
) -> None:
    """Strict execution plan validation and invariant attestation."""
    resolved_root = Path(repo_root).resolve()
    resolved_contract = (
        contract_path
        if contract_path.is_absolute()
        else (resolved_root / contract_path)
    )
    validate_payload_against_schema(plan, "execution_plan", resolved_contract)

    base_sha = plan.get("base_sha")
    exp_base_sha = plan.get("experiment_base_sha")
    if (
        base_sha != EXPERIMENT_BASE_SHA
        or exp_base_sha != EXPERIMENT_BASE_SHA
    ):
        raise ValueError(
            f"Execution plan base SHAs must equal '{EXPERIMENT_BASE_SHA}', "
            f"got base_sha='{base_sha}', experiment_base_sha='{exp_base_sha}'"
        )

    current_harness = resolve_harness_sha(repo_root=resolved_root)
    if plan.get("harness_sha") != current_harness:
        plan_h = plan.get("harness_sha")
        raise ValueError(
            f"Execution plan harness_sha '{plan_h}' does not match "
            f"current harness HEAD '{current_harness}'"
        )

    if plan.get("arm_order_seed") != ARM_ORDER_SEED_PREFIX:
        plan_seed = plan.get("arm_order_seed")
        raise ValueError(
            f"Execution plan arm_order_seed must be "
            f"'{ARM_ORDER_SEED_PREFIX}', got '{plan_seed}'"
        )

    plan_tiers = plan.get("tiers")
    if not isinstance(plan_tiers, list) or len(plan_tiers) == 0:
        raise ValueError("Execution plan tiers must be a non-empty list")
    if len(plan_tiers) != len(set(plan_tiers)):
        raise ValueError(
            f"Execution plan tiers contain duplicates: {plan_tiers}"
        )

    plan_replicates = plan.get("replicates")
    if not isinstance(plan_replicates, int) or plan_replicates < 1:
        raise ValueError(
            f"Execution plan replicates must be an integer >= 1, "
            f"got {plan_replicates}"
        )

    cfg_file = (
        config_path
        if config_path.is_absolute()
        else (resolved_root / config_path)
    )
    if not cfg_file.is_file():
        raise FileNotFoundError(f"Evaluation config missing: {cfg_file}")
    tiers_cfg = json.loads(cfg_file.read_text(encoding="utf-8")).get(
        "tiers", {}
    )

    for pt in plan_tiers:
        if pt not in tiers_cfg or not isinstance(tiers_cfg[pt], list):
            raise ValueError(
                f"Plan tier '{pt}' is not a valid non-rollup tier in "
                f"{cfg_file}"
            )

    trial_units = plan.get("trial_units")
    if not isinstance(trial_units, list) or len(trial_units) == 0:
        raise ValueError("Execution plan trial_units must be a non-empty list")

    resolved_tasks_dir = (
        tasks_dir
        if tasks_dir.is_absolute()
        else (resolved_root / tasks_dir)
    )

    seen_trial_ids: set[str] = set()
    seen_tuples: set[tuple[str, str, str, int]] = set()
    group_map: dict[tuple[str, int], list[dict[str, Any]]] = {}

    for i, unit in enumerate(trial_units):
        ord_idx = unit.get("order_index")
        t_ord_idx = unit.get("trial_order_index")
        if ord_idx != i or t_ord_idx != i:
            raise ValueError(
                f"Unit {i} has invalid order index: order_index={ord_idx}, "
                f"trial_order_index={t_ord_idx}, expected {i}"
            )

        if (
            unit.get("experiment_base_sha") != plan["experiment_base_sha"]
            or unit.get("harness_sha") != plan["harness_sha"]
        ):
            raise ValueError(f"Unit {i} SHAs mismatch plan SHAs")

        tid = str(unit.get("trial_id", ""))
        if (
            not tid
            or not re.match(r"^[a-zA-Z0-9_\-]+$", tid)
            or Path(tid).name != tid
            or tid.startswith(".")
        ):
            raise ValueError(f"Unit {i} has unsafe trial_id '{tid}'")
        if tid in seen_trial_ids:
            raise ValueError(f"Duplicate trial_id '{tid}' in unit {i}")
        seen_trial_ids.add(tid)

        tier = str(unit.get("tier", ""))
        if tier not in plan_tiers:
            raise ValueError(
                f"Unit {i} tier '{tier}' does not belong to plan "
                f"tiers {plan_tiers}"
            )

        replicate = int(unit.get("replicate", 0))
        if replicate < 1 or replicate > plan_replicates:
            raise ValueError(
                f"Unit {i} replicate {replicate} out of range "
                f"1..{plan_replicates}"
            )

        task_id = str(unit.get("task_id", ""))
        arm = str(unit.get("arm", ""))
        unit_tup = (tier, task_id, arm, replicate)
        if unit_tup in seen_tuples:
            raise ValueError(f"Duplicate unit tuple {unit_tup} in unit {i}")
        seen_tuples.add(unit_tup)

        task_file = str(unit.get("task_file", ""))
        if (
            not task_file
            or Path(task_file).name != task_file
            or ".." in task_file
            or task_file.startswith("/")
        ):
            raise ValueError(
                f"Unit {i} has unsafe task_file basename '{task_file}'"
            )

        if task_file not in tiers_cfg[tier]:
            raise ValueError(
                f"Unit {i} task_file '{task_file}' not in tier '{tier}' list"
            )

        det_selected = select_deterministic_task(
            EXPERIMENT_BASE_SHA, tier, tiers_cfg[tier]
        )
        if task_file != det_selected:
            raise ValueError(
                f"Unit {i} task_file '{task_file}' does not match "
                f"deterministic selection '{det_selected}' for tier '{tier}'"
            )

        t_path = resolved_tasks_dir / task_file
        if not t_path.is_file():
            raise FileNotFoundError(
                f"Unit {i} task file not found on disk: {t_path}"
            )
        task_data = json.loads(t_path.read_text(encoding="utf-8"))
        expected_task_id = str(task_data.get("id", Path(task_file).stem))
        if task_id != expected_task_id:
            raise ValueError(
                f"Unit {i} task_id '{task_id}' does not match task file id "
                f"'{expected_task_id}'"
            )

        group_key = (tier, replicate)
        group_map.setdefault(group_key, []).append(unit)

    unit_tiers_ordered: list[str] = []
    seen_tiers_ordered: set[str] = set()
    for u in trial_units:
        ut = str(u.get("tier", ""))
        if ut not in seen_tiers_ordered:
            seen_tiers_ordered.add(ut)
            unit_tiers_ordered.append(ut)
    if unit_tiers_ordered != plan_tiers:
        raise ValueError(
            f"Ordered unique tiers from trial units {unit_tiers_ordered} "
            f"do not match plan tiers {plan_tiers}"
        )

    for pt in plan_tiers:
        for r in range(1, plan_replicates + 1):
            key = (pt, r)
            if key not in group_map:
                raise ValueError(
                    f"Execution plan missing group for tier '{pt}' "
                    f"replicate {r}"
                )
    if len(group_map) != len(plan_tiers) * plan_replicates:
        raise ValueError(
            f"Execution plan has {len(group_map)} groups, "
            f"expected {len(plan_tiers) * plan_replicates}"
        )

    for (tier, replicate), group in group_map.items():
        if len(group) != len(ARMS):
            raise ValueError(
                f"Tier '{tier}' rep {replicate} has {len(group)} arms, "
                f"expected {len(ARMS)}"
            )
        group_task_id = group[0]["task_id"]
        expected_arm_order = deterministic_arm_order(
            EXPERIMENT_BASE_SHA, group_task_id, replicate, list(ARMS.keys())
        )
        actual_arms = [u["arm"] for u in group]
        if actual_arms != expected_arm_order:
            raise ValueError(
                f"Tier '{tier}' rep {replicate} arms {actual_arms} do not "
                f"match canonical deterministic order {expected_arm_order}"
            )


def resolve_canonical_adapter_context(
    repo_root: Path = Path("."),
    expected_model: str = DEFAULT_MODEL,
    expected_digest: str | None = None,
    tool_signatures: dict[str, Any] | None = None,
) -> AdapterRuntimeContext:
    """Resolve and validate canonical repository adapter context."""
    sigs = (
        tool_signatures
        if tool_signatures is not None
        else _get_mcp_tool_signatures()
    )
    state_dir = repo_root / ".mighty-mouse"
    cfg_file = state_dir / "mcp-adapter.json"
    if not cfg_file.is_file():
        raise RuntimeError(
            f"Canonical MCP adapter configuration missing at {cfg_file}. "
            "Fail closed before generation."
        )

    try:
        ctx = HostAdapter.resolve_adapter_context(
            workspace=str(repo_root),
            state_dir=str(state_dir),
            tool_signatures=sigs,
            contract_version=MCP_TOOL_CONTRACT_VERSION,
        )
    except Exception as exc:
        raise RuntimeError(
            f"Canonical adapter context resolution failed: {exc}"
        ) from exc

    if ctx.model_source != "ollama":
        raise ValueError(
            f"Canonical adapter model_source must be 'ollama', "
            f"got '{ctx.model_source}'"
        )
    if ctx.ollama_model != expected_model:
        raise ValueError(
            f"Canonical adapter ollama_model must be '{expected_model}', "
            f"got '{ctx.ollama_model}'"
        )
    if (
        expected_digest
        and ctx.model_identity.artifact_digest != expected_digest
    ):
        raise ValueError(
            f"Canonical adapter model digest "
            f"'{ctx.model_identity.artifact_digest}' does not match "
            f"expected digest '{expected_digest}'"
        )
    return ctx


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
    expected_digest: str | None = None,
    timeout_sec: int = 120,
    usage_capture: CaptureOllamaUsage | None = None,
    repo_root: Path = Path("."),
) -> dict[str, Any]:
    """Execute a single trial unit across one of the five arms."""
    repo_root = Path(repo_root).resolve()
    target_harness = (
        harness_sha
        or plan_unit.get("harness_sha")
        or resolve_harness_sha(repo_root=repo_root)
    )
    sigs = (
        tool_signatures
        if tool_signatures is not None
        else _get_mcp_tool_signatures()
    )
    arm = plan_unit["arm"]
    if arm not in ARMS:
        raise ValueError(f"Unknown arm '{arm}' in plan unit")

    arm_def = ARMS[arm]
    task_file_name = plan_unit["task_file"]
    task_json_path = (
        tasks_dir / task_file_name
        if tasks_dir.is_absolute()
        else repo_root / tasks_dir / task_file_name
    )
    if not task_json_path.is_file():
        raise FileNotFoundError(f"Task file not found: {task_json_path}")

    task_bytes = task_json_path.read_bytes()
    task_sha256 = compute_sha256_bytes(task_bytes)
    task_config = json.loads(task_bytes.decode("utf-8"))

    # Baseline-to-harness delta check as an execution gate
    delta_ok, changed_or_unapproved = verify_baseline_harness_delta(
        base_sha, target_harness, repo_root=repo_root
    )
    if not delta_ok:
        raise RuntimeError(
            "Baseline-to-harness delta check failed closed before trial "
            f"execution. Unapproved paths: {changed_or_unapproved}"
        )
    changed_paths = changed_or_unapproved

    server_info = provenance_info or check_ollama_provenance(
        ollama_host, ollama_model
    )
    if not server_info.get("available") or not server_info.get("model_digest"):
        raise RuntimeError(
            "Ollama provenance unavailable or missing model digest for "
            f"'{ollama_model}' at {ollama_host}. "
            "Fail closed before generation."
        )
    model_digest = server_info["model_digest"]
    if expected_digest is not None and model_digest != expected_digest:
        raise RuntimeError(
            f"Ollama model digest '{model_digest}' does not match expected "
            f"digest '{expected_digest}'. Fail closed before generation."
        )

    trial_id = plan_unit["trial_id"]
    trial_workspace = workspace_root / trial_id
    iso_workspace = workspace_root / f"{trial_id}_verify"

    # Enforce fresh, empty application workspace
    prepare_fresh_trial_workspace(
        trial_workspace,
        iso_workspace if arm in ("mm_swarm", "mm_swarm_recovery") else None,
        workspace_root=workspace_root,
    )

    canonical_config_path = repo_root / "configs/mighty_mouse_v1.yaml"
    if not canonical_config_path.is_file():
        raise FileNotFoundError(
            f"Canonical model config missing at {canonical_config_path}. "
            "Fail closed before generation."
        )
    canonical_state_dir = repo_root / ".mighty-mouse"
    if (
        arm != "control_once"
        and not (canonical_state_dir / "mcp-adapter.json").is_file()
    ):
        raise FileNotFoundError(
            "Canonical adapter state missing at "
            f"{canonical_state_dir / 'mcp-adapter.json'}. "
            "Fail closed before generation."
        )

    resolved_ctx: AdapterRuntimeContext | None = None
    if arm != "control_once":
        resolved_ctx = resolve_canonical_adapter_context(
            repo_root=repo_root,
            expected_model=ollama_model,
            expected_digest=model_digest,
            tool_signatures=sigs,
        )

    adapter = HostAdapter()
    primary_exception: Exception | None = None
    execution_stage: str | None = None
    first_verif: dict[str, Any] | None = None
    terminal_verif: dict[str, Any] | None = None
    recovery_eligible = False
    recovery_gate_reason: str | None = None
    recovery_attempted = False
    recovery_completed = False
    terminal_failure_cat: str | None = None

    active_capture = usage_capture or CaptureOllamaUsage()
    active_capture.configure_trial(output_dir, trial_id)
    ctx_mgr = active_capture if usage_capture is None else None

    wall_start = time.monotonic()
    rec_exception: Exception | None = None
    try:
        if ctx_mgr is not None:
            ctx_mgr.__enter__()

        active_capture.set_phase("primary")

        # 1. Primary Execution
        if arm == "control_once":
            t0 = time.monotonic()
            raw_response: str | None = None
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
                    latency_seconds=float(
                        meta.get("latency_seconds", time.monotonic() - t0)
                    ),
                    raw_response_text=raw_response,
                )
            except Exception as exc:
                primary_exception = exc
                execution_stage = "generation"
                active_capture.record_generation(
                    phase="primary",
                    model=ollama_model,
                    prompt_tokens=None,
                    completion_tokens=None,
                    total_tokens=None,
                    latency_seconds=time.monotonic() - t0,
                    raw_response_text=None,
                )

            if primary_exception is None and raw_response is not None:
                try:
                    applied_files = apply_response(
                        ResponseApplicationRequest(
                            raw_response=raw_response,
                            policy=ResponseApplicationPolicy(
                                workspace_root=str(trial_workspace),
                            ),
                        )
                    )
                    if not applied_files:
                        execution_stage = "schema"
                        raise ValueError(
                            "No valid file blocks identified in model "
                            "response."
                        )
                except Exception as exc:
                    primary_exception = exc
                    exc_str = str(exc).lower()
                    if (
                        "no valid file" in exc_str
                        or "ambiguous" in exc_str
                        or "xml leakage" in exc_str
                        or "oversized" in exc_str
                    ):
                        execution_stage = "schema"
                    else:
                        execution_stage = "application"

        elif arm in ("mm_single", "mm_single_recovery"):
            try:
                adapter.solve(
                    workspace=str(trial_workspace),
                    p_cfg_path=str(canonical_config_path),
                    task_input=str(task_json_path.resolve()),
                    state_dir=str(canonical_state_dir),
                    tool_signatures=sigs,
                )
            except Exception as exc:
                primary_exception = exc
                exc_str = str(exc).lower()
                if "generate" in exc_str or "ollama" in exc_str:
                    execution_stage = "generation"
                elif "schema" in exc_str or "parse" in exc_str:
                    execution_stage = "schema"
                else:
                    execution_stage = "application"

        elif arm in ("mm_swarm", "mm_swarm_recovery"):
            try:
                adapter.solve_swarm(
                    workspace=str(trial_workspace),
                    task_input=json.dumps(task_config),
                    verification_workspace=str(iso_workspace),
                    state_dir=str(canonical_state_dir),
                    concurrency=SWARM_CONCURRENCY,
                    tool_signatures=sigs,
                    task_config=task_config,
                    timeout_sec=timeout_sec,
                )
            except Exception as exc:
                primary_exception = exc
                exc_str = str(exc).lower()
                if "generate" in exc_str or "ollama" in exc_str:
                    execution_stage = "generation"
                elif "schema" in exc_str or "parse" in exc_str:
                    execution_stage = "schema"
                else:
                    execution_stage = "application"

        # 2. Authoritative First Verification
        first_verif = None
        first_verifier_completed = False
        first_verifier_exception: Exception | None = None
        if trial_workspace.is_dir():
            try:
                first_verif = verify_task(
                    task_config, workspace=str(trial_workspace)
                )
                if (
                    not isinstance(first_verif, dict)
                    or first_verif.get("status") not in ("success", "fail")
                ):
                    first_verifier_completed = False
                    raw_st = (
                        first_verif.get("status")
                        if isinstance(first_verif, dict)
                        else type(first_verif)
                    )
                    first_verifier_exception = RuntimeError(
                        f"Malformed first verifier status: {raw_st}"
                    )
                else:
                    first_verifier_completed = True
            except Exception as exc:
                first_verifier_completed = False
                first_verifier_exception = exc

        first_err = (
            first_verifier_exception is not None
            or not first_verifier_completed
        )
        if first_err:
            first_passed = False
            first_failure_cat = "verifier_error"
        elif primary_exception is not None:
            # Primary execution failed; trial cannot pass even if
            # verifier happens to be permissive
            first_passed = False
            first_failure_cat = classify_failure(
                first_verif, exception=primary_exception, stage=execution_stage
            )
        elif first_verif.get("status") == "success":
            first_passed = True
            first_failure_cat = None
        elif first_verif.get("status") == "fail":
            first_passed = False
            first_failure_cat = classify_failure(first_verif)
        else:
            first_passed = False
            first_failure_cat = "verifier_error"

        terminal_passed = first_passed
        terminal_verif = first_verif
        terminal_failure_cat = first_failure_cat
        terminal_verifier_completed = first_verifier_completed
        re_verif_exception: Exception | None = None

        # 3. Recovery Handling
        # Recovery is permitted ONLY if:
        # - arm has recovery_enabled
        # - primary execution completed without uncaught primary exception
        # - first verifier ran and completed without crashing
        # - first verification explicitly returned status == "fail"
        if (
            arm_def.recovery_enabled
            and primary_exception is None
            and first_verifier_completed
            and first_verifier_exception is None
            and isinstance(first_verif, dict)
            and first_verif.get("status") == "fail"
        ):
            assert resolved_ctx is not None
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
            resolved_event = ResolvedHostHookEvent(
                event=recovery_event,
                runtime_context=resolved_ctx,
            )
            verif_summary = HookVerificationSummary(
                occurred=True,
                passed=False,
                summary=(first_verif or {}).get(
                    "reason", "Primary verification failed"
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
                    p_cfg_path=str(canonical_config_path),
                    task_input_path=str(task_json_path.resolve()),
                )
                attempt = None
                try:
                    attempt = execute_recovery_attempt(
                        rec_request,
                        feedback_str=verif_summary.summary,
                    )
                    recovery_attempted = attempt.attempted
                    recovery_completed = attempt.completed
                except Exception as exc:
                    rec_exception = exc
                    recovery_attempted = True
                    recovery_completed = False
                    logger.error("Recovery execution exception: %s", exc)

                if recovery_completed and attempt is not None:
                    try:
                        terminal_verif = verify_task(
                            task_config, workspace=str(trial_workspace)
                        )
                        is_valid_term = (
                            isinstance(terminal_verif, dict)
                            and terminal_verif.get("status")
                            in ("success", "fail")
                        )
                        if not is_valid_term:
                            terminal_passed = False
                            terminal_failure_cat = "verifier_error"
                            terminal_verifier_completed = False
                            t_raw_st = (
                                terminal_verif.get("status")
                                if isinstance(terminal_verif, dict)
                                else type(terminal_verif)
                            )
                            re_verif_exception = RuntimeError(
                                f"Malformed re-verifier status: {t_raw_st}"
                            )
                        else:
                            terminal_verifier_completed = True
                            if terminal_verif.get("status") == "success":
                                terminal_passed = True
                                terminal_failure_cat = None
                            else:
                                terminal_passed = False
                                terminal_failure_cat = classify_failure(
                                    terminal_verif, is_recovery=True
                                )
                    except Exception as exc:
                        terminal_passed = False
                        terminal_failure_cat = "verifier_error"
                        terminal_verifier_completed = False
                        re_verif_exception = exc
                        terminal_verif = None
                else:
                    terminal_passed = False
                    terminal_failure_cat = "recovery_failed"

    finally:
        wall_latency = round(time.monotonic() - wall_start, 4)
        if ctx_mgr is not None:
            ctx_mgr.__exit__(None, None, None)

    # 4. Usage Aggregation
    events = active_capture.events
    primary_events = [e for e in events if e.get("phase") == "primary"]
    recovery_events = [e for e in events if e.get("phase") == "recovery"]

    def _sum_tokens(ev_list: list[dict[str, Any]], field: str) -> int | None:
        vals = [e[field] for e in ev_list]
        if any(v is None for v in vals):
            return None
        return sum(vals)

    p_prompt_tok = _sum_tokens(primary_events, "prompt_tokens")
    p_comp_tok = _sum_tokens(primary_events, "completion_tokens")
    r_prompt_tok = _sum_tokens(recovery_events, "prompt_tokens")
    r_comp_tok = _sum_tokens(recovery_events, "completion_tokens")

    if (
        p_prompt_tok is not None
        and p_comp_tok is not None
        and r_prompt_tok is not None
        and r_comp_tok is not None
    ):
        tot_tok: int | None = (
            p_prompt_tok + p_comp_tok + r_prompt_tok + r_comp_tok
        )
    else:
        tot_tok = None

    model_lat = round(sum(e["latency_seconds"] for e in events), 4)

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
        "recovery_exception": (
            str(rec_exception) if rec_exception else None
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

    if arm == "control_once":
        prov_record: dict[str, Any] = {
            "provider": "ollama",
            "ollama_version": str(server_info.get("version", "unknown")),
            "model": ollama_model,
            "model_digest": model_digest,
            "agent_config_sha256": None,
            "prompt_template_sha256": compute_sha256_bytes(
                BARE_PROMPT_TEMPLATE.encode("utf-8")
            ),
            "execution_profile_id": None,
            "tool_contract_digest": None,
            "runtime_version": None,
            "runtime_kind": None,
            "experiment_base_sha": base_sha,
            "harness_sha": target_harness,
            "baseline_to_harness_changed_paths": changed_paths,
        }
    else:
        assert resolved_ctx is not None
        prov_record = {
            "provider": "ollama",
            "ollama_version": str(server_info.get("version", "unknown")),
            "model": resolved_ctx.ollama_model or ollama_model,
            "model_digest": resolved_ctx.model_identity.artifact_digest,
            "agent_config_sha256": compute_sha256_file(canonical_config_path),
            "prompt_template_sha256": (
                resolved_ctx.execution_profile.prompt_template_digest
            ),
            "execution_profile_id": (
                resolved_ctx.execution_profile.profile_id
            ),
            "tool_contract_digest": (
                resolved_ctx.execution_profile.tool_contract_digest
            ),
            "runtime_version": (
                resolved_ctx.execution_profile.runtime_version
            ),
            "runtime_kind": (
                resolved_ctx.execution_profile.runtime_kind
            ),
            "experiment_base_sha": base_sha,
            "harness_sha": target_harness,
            "baseline_to_harness_changed_paths": changed_paths,
        }

    infra_error: str | None = None
    if first_failure_cat == "verifier_error":
        infra_error = f"First verifier crash: {first_verifier_exception}"
    elif terminal_failure_cat == "verifier_error":
        infra_error = f"Re-verifier crash: {re_verif_exception}"

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
        "provenance": prov_record,
        "execution": {
            "swarm_concurrency": (
                SWARM_CONCURRENCY if "swarm" in arm else 1
            ),
            "internal_attempts": len(primary_events),
            "generation_calls": active_capture.generation_calls,
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
            "token_coverage_complete": (
                active_capture.token_coverage_complete
                and (tot_tok is not None)
            ),
            "first_verifier_completed": first_verifier_completed,
            "terminal_verifier_completed": terminal_verifier_completed,
            "verifier_completed": terminal_verifier_completed,
            "infrastructure_error": infra_error,
            "trace_artifact_relpath": trace_relpath,
            "trace_artifact_sha256": trace_sha256,
            "raw_response_artifacts": active_capture.raw_response_artifacts,
        },
    }

    resolved_contract = (
        contract_path
        if contract_path.is_absolute()
        else (repo_root / contract_path)
    )
    validate_payload_against_schema(
        trial_record, "trial_record", resolved_contract
    )

    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)
        record_file = output_dir / f"{trial_id}.json"
        record_file.write_text(
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
    repo_root: Path = Path("."),
) -> dict[str, Any]:
    """Execute all units in an execution plan under SingleInstanceLock."""
    from eval.reliability_matrix import run_preflight

    repo_root = Path(repo_root).resolve()
    resolved_contract = (
        contract_path
        if contract_path.is_absolute()
        else (repo_root / contract_path)
    )

    # Attest and validate loaded execution plan before any side effects
    validate_execution_plan(
        plan,
        contract_path=resolved_contract,
        config_path=config_path,
        tasks_dir=tasks_dir,
        repo_root=repo_root,
    )

    target_base = plan.get(
        "experiment_base_sha", plan.get("base_sha", EXPERIMENT_BASE_SHA)
    )
    target_harness = plan.get("harness_sha") or resolve_harness_sha(
        repo_root=repo_root
    )
    asserted_harness = resolve_harness_sha(repo_root=repo_root)

    if target_base != EXPERIMENT_BASE_SHA:
        raise ValueError(
            f"Execution plan experiment_base_sha '{target_base}' does not "
            f"match asserted base '{EXPERIMENT_BASE_SHA}'"
        )
    if plan.get("harness_sha") and plan["harness_sha"] != asserted_harness:
        raise ValueError(
            f"Execution plan harness_sha '{plan['harness_sha']}' does not "
            f"match asserted harness '{asserted_harness}'"
        )

    delta_ok, changed_or_unapproved = verify_baseline_harness_delta(
        target_base, target_harness, repo_root=repo_root
    )
    if not delta_ok:
        raise RuntimeError(
            "Baseline-to-harness delta check failed closed before generation. "
            f"Unapproved paths changed: {changed_or_unapproved}"
        )
    changed_paths = changed_or_unapproved

    lock_file = (
        lock_path
        if lock_path is not None
        else (repo_root / "logs/eval_runner.lock")
    )
    lock = SingleInstanceLock(lock_file)
    with lock:
        output_dir.mkdir(parents=True, exist_ok=True)
        if dry_run:
            # dry_run=True guarantees ZERO execution and ZERO generation
            summary = {
                "schema_version": SCHEMA_VERSION,
                "experiment_id": plan["experiment_id"],
                "experiment_base_sha": target_base,
                "base_sha": target_base,
                "harness_sha": target_harness,
                "baseline_to_harness_changed_paths": changed_paths,
                "trial_count": 0,
                "arms": sorted(
                    {unit["arm"] for unit in plan.get("trial_units", [])}
                ),
                "metrics": {
                    "arms": {},
                    "total_trials": 0,
                    "total_analyzable": 0,
                    "total_passed": 0,
                    "total_infrastructure_excluded": 0,
                    "total_tokens": None,
                },
                "status": "dry_run",
                "stop_reason": None,
                "dry_run": True,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            validate_payload_against_schema(
                summary, "run_summary", resolved_contract
            )
            summary_file = output_dir / "run_summary.json"
            summary_file.write_text(
                json.dumps(summary, indent=2), encoding="utf-8"
            )
            return summary

        preflight_report = run_preflight(
            experiment_id=plan["experiment_id"],
            base_sha=target_base,
            harness_sha=target_harness,
            output_dir=output_dir,
            contract_path=contract_path,
            config_path=config_path,
            tasks_dir=tasks_dir,
            ollama_host=ollama_host,
            ollama_model=ollama_model,
            required_tiers=plan.get("tiers", list(P1_TIERS)),
            lock_instance=lock,
            repo_root=repo_root,
        )
        if not preflight_report.get("preflight_passed"):
            reasons = preflight_report.get("blocking_reasons", [])
            raise RuntimeError(
                f"Scoped preflight failed before execution: {reasons}"
            )

        # Authoritative frozen provenance from scoped preflight
        frozen_digest = preflight_report["ollama_server"].get("model_digest")
        if not frozen_digest or frozen_digest == "unknown":
            raise RuntimeError(
                "Preflight model digest missing or unknown; failing closed."
            )
        frozen_provenance = preflight_report["ollama_server"]

        trial_records: list[dict[str, Any]] = []
        stop_reason: str | None = None
        status = "completed"

        for unit in plan.get("trial_units", []):
            # Check model provenance before each trial
            live_prov = check_ollama_provenance(ollama_host, ollama_model)
            if (
                not live_prov.get("available")
                or live_prov.get("model_digest") != frozen_digest
            ):
                live_dig = live_prov.get("model_digest")
                stop_reason = (
                    f"Model digest changed from frozen '{frozen_digest}' "
                    f"to '{live_dig}'. Aborting."
                )
                status = "aborted"
                break

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
                provenance_info=frozen_provenance,
                expected_digest=frozen_digest,
                repo_root=repo_root,
            )
            trial_records.append(rec)

            # Evaluate established stop conditions
            rec_tid = rec["identity"]["trial_id"]
            if (
                rec.get("validity", {}).get("infrastructure_error") is not None
                or rec.get("verification", {}).get("first_failure_category")
                in ("verifier_error", "infrastructure_error")
                or rec.get("verification", {}).get("terminal_failure_category")
                in ("verifier_error", "infrastructure_error")
            ):
                infra_msg = (
                    rec.get("validity", {}).get("infrastructure_error")
                    or rec.get("verification", {}).get(
                        "terminal_failure_category"
                    )
                    or rec.get("verification", {}).get(
                        "first_failure_category"
                    )
                )
                stop_reason = (
                    f"Infrastructure error in trial {rec_tid}: {infra_msg}"
                )
            elif not rec.get("validity", {}).get("provenance_complete"):
                stop_reason = (
                    f"Provenance incomplete in trial {rec_tid}"
                )
            elif not rec.get("validity", {}).get(
                "terminal_verifier_completed"
            ):
                stop_reason = (
                    f"Terminal verifier incomplete in trial {rec_tid}"
                )
            elif not rec.get("validity", {}).get("token_coverage_complete"):
                stop_reason = (
                    f"Token coverage incomplete in trial {rec_tid}"
                )

            if stop_reason is not None:
                status = "aborted"
                break

        arm_counts: dict[str, dict[str, int]] = {}
        for rec in trial_records:
            arm_name = rec["identity"]["arm"]
            if arm_name not in arm_counts:
                arm_counts[arm_name] = {
                    "total": 0,
                    "analyzable": 0,
                    "passed": 0,
                    "infrastructure_excluded": 0,
                }
            arm_counts[arm_name]["total"] += 1
            is_infra_error = (
                rec.get("validity", {}).get("infrastructure_error") is not None
                or rec.get("verification", {}).get("first_failure_category")
                in ("verifier_error", "infrastructure_error")
                or rec.get("verification", {}).get("terminal_failure_category")
                in ("verifier_error", "infrastructure_error")
            )
            if is_infra_error:
                arm_counts[arm_name]["infrastructure_excluded"] += 1
            else:
                arm_counts[arm_name]["analyzable"] += 1
                if rec["verification"]["terminal_passed"]:
                    arm_counts[arm_name]["passed"] += 1

        total_analyzable = sum(ac["analyzable"] for ac in arm_counts.values())
        total_passed = sum(ac["passed"] for ac in arm_counts.values())
        total_infra_excluded = sum(
            ac["infrastructure_excluded"] for ac in arm_counts.values()
        )

        all_tokens = [r["cost"]["total_tokens"] for r in trial_records]
        if any(t is None for t in all_tokens) or not trial_records:
            run_total_tokens: int | None = None
        else:
            run_total_tokens = sum(all_tokens)  # type: ignore[arg-type]

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
                "total_trials": len(trial_records),
                "total_analyzable": total_analyzable,
                "total_passed": total_passed,
                "total_infrastructure_excluded": total_infra_excluded,
                "total_tokens": run_total_tokens,
            },
            "status": status,
            "stop_reason": stop_reason,
            "dry_run": False,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        validate_payload_against_schema(
            summary, "run_summary", resolved_contract
        )
        summary_file = output_dir / "run_summary.json"
        summary_file.write_text(
            json.dumps(summary, indent=2), encoding="utf-8"
        )
        return summary
