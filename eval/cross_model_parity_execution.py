"""Cross-Model Parity Pilot Executor (Milestone 13 Ticket 04).

Implements the 12-trial execution engine for the frozen cross-model pilot,
supporting control_once and mm_single arms across llama31_8b_q4km and
qwen25_7b_q4km candidates under an immutable canonical configuration and
authoritatively bounded execution/provenance layers.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
from typing import Any, Dict, List, Optional, Tuple
import urllib.request
import yaml

from eval.cross_model_parity import (
    DEFAULT_CONFIG_PATH,
    DEFAULT_CONTRACT_PATH,
    FROZEN_ANCHOR_TASKS,
    FROZEN_CANDIDATES,
    FROZEN_PHASE_B_TASKS,
    LOCK_FILE_PATH,
    M13_EFFECTIVE_CONTEXT_LIMIT,
    M13_EXECUTION_BASE_SHA,
    M13_EXPERIMENT_BASE_SHA,
    M13_EXPERIMENT_ID,
    M13_PHASE_B_EXECUTION_BASE_SHA,
    M13_PHASE_B_EXPERIMENT_ID,
    CrossModelCandidate,
    CrossModelPlanUnit,
    get_current_git_sha,
    materialize_execution_plan,
    project_candidate_config,
    run_preflight,
    validate_execution_plan,
    validate_payload_against_schema,
    verify_base_to_harness_delta,
)
from eval.reliability_matrix_execution import (
    CaptureOllamaUsage,
    classify_failure,
    prepare_fresh_trial_workspace,
    request_control_generation,
)
from eval.run_bare_baseline import build_prompt as build_bare_prompt
from eval.runner_lock import SingleInstanceLock
from mighty_mouse.host.adapter import (
    ADAPTER_CONFIG_FILENAME,
    AdapterRuntimeContext,
    HostAdapter,
    MCP_TOOL_CONTRACT_VERSION,
)
from mighty_mouse.orchestrator import response_application as _ra
from mighty_mouse.orchestrator.response_application import (
    ResponseApplicationPolicy,
    ResponseApplicationRequest,
)
from mighty_mouse.services.verifiers.run_benchmark import verify_task
from mighty_mouse_mcp.server import _get_mcp_tool_signatures

_apply_response = getattr(_ra, "apply_response")

CONTROLLED_MODEL_CLASSES = frozenset(
    {"local-small", "local-medium", "local-large", "unknown"}
)


def _atomic_write_json(
    target_path: Path, data: Dict[str, Any], allow_overwrite: bool = False
) -> None:
    """Crash-safe same-filesystem atomic write rejecting accidental overwrite.
    """
    if not allow_overwrite and target_path.exists():
        raise FileExistsError(f"Target file already exists: {target_path}")
    target_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = target_path.with_name(
        f"{target_path.name}.tmp.{os.getpid()}_{time.monotonic_ns()}"
    )
    try:
        content = json.dumps(data, indent=2, sort_keys=True) + "\n"
        temp_path.write_text(content, encoding="utf-8")
        temp_path.replace(target_path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


DEFAULT_OLLAMA_HOST = "http://127.0.0.1:11434"


def query_ollama_version(host: str = DEFAULT_OLLAMA_HOST) -> str:
    """Query current Ollama API version for continuity attestation."""
    req = urllib.request.Request(f"{host.rstrip('/')}/api/version")
    with urllib.request.urlopen(req, timeout=5) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        ver = data.get("version")
        if not ver or ver == "unknown":
            raise RuntimeError(f"Ollama API returned invalid version: {data}")
        return str(ver)


def prepare_candidate_runtime(
    candidate: CrossModelCandidate,
    local_adapter_context: AdapterRuntimeContext,
    support_dir: Path,
    config_path: Path = DEFAULT_CONFIG_PATH,
) -> Tuple[Path, str, Path, str]:
    """Derive ephemeral projected config and adapter identity for candidate."""
    if local_adapter_context.model_class not in CONTROLLED_MODEL_CLASSES:
        raise ValueError(
            f"Canonical runtime model class "
            f"'{local_adapter_context.model_class}' is not a supported "
            f"controlled class: {sorted(CONTROLLED_MODEL_CLASSES)}"
        )
    runtime_model_class = local_adapter_context.model_class

    support_dir.mkdir(parents=True, exist_ok=True)

    proj_cfg, proj_sha = project_candidate_config(
        candidate.model_tag, config_path
    )
    proj_cfg_path = (
        support_dir / f"projected_config_{candidate.candidate_id}.yaml"
    )
    serialized_cfg = yaml.dump(proj_cfg, sort_keys=True)
    proj_cfg_path.write_text(serialized_cfg, encoding="utf-8")
    actual_proj_sha = hashlib.sha256(
        serialized_cfg.encode("utf-8")
    ).hexdigest()
    if actual_proj_sha != proj_sha:
        raise ValueError(
            f"Projected config SHA mismatch: {actual_proj_sha} != {proj_sha}"
        )

    cfg_parent = config_path.parent
    sys_prompt_name = proj_cfg.get("system_prompt_path", "system_prompt.txt")
    canon_sys_path = cfg_parent / sys_prompt_name
    if canon_sys_path.is_file():
        target_sys_path = support_dir / sys_prompt_name
        target_sys_path.parent.mkdir(parents=True, exist_ok=True)
        sys_bytes = canon_sys_path.read_bytes()
        target_sys_path.write_bytes(sys_bytes)
        if (
            hashlib.sha256(target_sys_path.read_bytes()).hexdigest()
            != hashlib.sha256(sys_bytes).hexdigest()
        ):
            raise ValueError(
                f"System prompt copy corrupted: {sys_prompt_name}"
            )

    for seg_rel in proj_cfg.get("prompt_segments", []):
        canon_seg_path = cfg_parent / seg_rel
        if canon_seg_path.is_file():
            target_seg_path = support_dir / seg_rel
            target_seg_path.parent.mkdir(parents=True, exist_ok=True)
            seg_bytes = canon_seg_path.read_bytes()
            target_seg_path.write_bytes(seg_bytes)
            if (
                hashlib.sha256(target_seg_path.read_bytes()).hexdigest()
                != hashlib.sha256(seg_bytes).hexdigest()
            ):
                raise ValueError(f"Prompt segment copy corrupted: {seg_rel}")

    tool_signatures = _get_mcp_tool_signatures()
    adapter_cfg = HostAdapter.build_adapter_config(
        repository=local_adapter_context.repository,
        model_digest=candidate.model_digest,
        model_class=runtime_model_class,
        effective_context_limit=M13_EFFECTIVE_CONTEXT_LIMIT,
        runtime_kind=local_adapter_context.execution_profile.runtime_kind,
        runtime_version=(
            local_adapter_context.execution_profile.runtime_version
        ),
        ollama_model=candidate.model_tag,
        tool_signatures=tool_signatures,
        contract_version=MCP_TOOL_CONTRACT_VERSION,
    )

    adapter_cfg_path = support_dir / ADAPTER_CONFIG_FILENAME
    adapter_bytes = (
        json.dumps(adapter_cfg, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    adapter_cfg_path.write_bytes(adapter_bytes)
    adapter_sha = hashlib.sha256(adapter_bytes).hexdigest()
    if (
        hashlib.sha256(adapter_cfg_path.read_bytes()).hexdigest()
        != adapter_sha
    ):
        raise ValueError("Adapter config disk SHA mismatch")

    HostAdapter.validate_adapter_config(
        adapter_cfg,
        tool_signatures=tool_signatures,
        contract_version=MCP_TOOL_CONTRACT_VERSION,
    )
    resolved = HostAdapter.resolve_adapter_context(
        workspace=str(support_dir),
        state_dir=str(support_dir),
        tool_signatures=tool_signatures,
        contract_version=MCP_TOOL_CONTRACT_VERSION,
    )
    if resolved.model_class != runtime_model_class:
        raise ValueError(
            f"Resolved model class mismatch: {resolved.model_class} != "
            f"{runtime_model_class}"
        )
    if resolved.model_identity.artifact_digest != candidate.model_digest:
        raise ValueError(
            f"Resolved model digest mismatch: "
            f"{resolved.model_identity.artifact_digest} != "
            f"{candidate.model_digest}"
        )
    if resolved.ollama_model != candidate.model_tag:
        raise ValueError(
            f"Resolved ollama model mismatch: {resolved.ollama_model} != "
            f"{candidate.model_tag}"
        )
    if (
        resolved.execution_profile.effective_context_limit
        != M13_EFFECTIVE_CONTEXT_LIMIT
    ):
        raise ValueError(
            f"Resolved effective context mismatch: "
            f"{resolved.execution_profile.effective_context_limit} != "
            f"{M13_EFFECTIVE_CONTEXT_LIMIT}"
        )

    return proj_cfg_path, proj_sha, adapter_cfg_path, adapter_sha


def execute_trial_unit(
    unit: Any,
    *,
    workspace_root: Path,
    support_root: Path,
    output_dir: Path,
    local_adapter_context: AdapterRuntimeContext,
    ollama_host: str = "http://127.0.0.1:11434",
    config_path: Path = DEFAULT_CONFIG_PATH,
    contract_path: Path = DEFAULT_CONTRACT_PATH,
    harness_sha: Optional[str] = None,
    ollama_version: Optional[str] = None,
    experiment_id: Optional[str] = None,
    execution_base_sha: Optional[str] = None,
) -> Dict[str, Any]:
    """Execute one cross-model trial unit with verification."""
    unit_exp_id = None
    unit_exec_base = None
    if isinstance(unit, dict):
        unit_exp_id = unit.get("experiment_id")
        unit_exec_base = unit.get("execution_base_sha")
        clean_unit = {
            k: v
            for k, v in unit.items()
            if k not in ("experiment_id", "execution_base_sha")
        }
        unit = CrossModelPlanUnit(**clean_unit)
    else:
        unit_exp_id = getattr(unit, "experiment_id", None)
        unit_exec_base = getattr(unit, "execution_base_sha", None)

    active_exp_id = experiment_id or unit_exp_id or M13_EXPERIMENT_ID
    if active_exp_id == M13_PHASE_B_EXPERIMENT_ID:
        expected_exec_base = M13_PHASE_B_EXECUTION_BASE_SHA
        task_registry = FROZEN_PHASE_B_TASKS
    elif active_exp_id == M13_EXPERIMENT_ID:
        expected_exec_base = M13_EXECUTION_BASE_SHA
        task_registry = FROZEN_ANCHOR_TASKS
    else:
        raise ValueError(f"Unsupported experiment_id: {active_exp_id}")

    if (
        execution_base_sha is not None
        and execution_base_sha != expected_exec_base
    ):
        raise ValueError(
            f"execution_base_sha mismatch for {active_exp_id}: "
            f"expected {expected_exec_base}, got {execution_base_sha}"
        )

    if harness_sha is None:
        harness_sha = get_current_git_sha()

    if ollama_version is None:
        try:
            req = urllib.request.Request(f"{ollama_host}/api/version")
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                ollama_version = data.get("version")
        except Exception:
            ollama_version = None
    if not ollama_version:
        raise RuntimeError(
            "Ollama version is unavailable before trial execution"
        )

    cand = FROZEN_CANDIDATES.get(unit.candidate_id)
    if cand is None:
        raise ValueError(f"Unknown candidate {unit.candidate_id}")
    task_def = task_registry.get(unit.task_id)
    if task_def is None:
        raise ValueError(
            f"Unknown task {unit.task_id} for experiment {active_exp_id}"
        )

    task_file_path = Path(unit.task_file)
    if not task_file_path.exists():
        raise FileNotFoundError(f"Task file missing: {unit.task_file}")
    actual_task_sha = hashlib.sha256(task_file_path.read_bytes()).hexdigest()
    if actual_task_sha != unit.task_sha256:
        raise ValueError(
            f"Task SHA-256 tampered: {actual_task_sha} != {unit.task_sha256}"
        )

    d1 = HostAdapter.resolve_ollama_model_digest(cand.model_tag)
    d2 = HostAdapter.resolve_ollama_model_digest(cand.model_tag)
    if d1 != d2 or d1 != cand.model_digest:
        raise ValueError(
            f"Candidate model digest unstable or changed: {d1} != "
            f"{cand.model_digest}"
        )

    changed_paths = verify_base_to_harness_delta(
        expected_exec_base, harness_sha
    )

    trial_ws = workspace_root / unit.trial_id / "workspace"
    prepare_fresh_trial_workspace(trial_ws, workspace_root=workspace_root)

    trial_sup = support_root / unit.trial_id / "support"
    if trial_sup.exists():
        raise ValueError(f"Support dir already exists: {trial_sup}")
    trial_sup.mkdir(parents=True, exist_ok=False)

    proj_cfg_path: Optional[Path] = None
    proj_sha: Optional[str] = None
    adapt_cfg_path: Optional[Path] = None
    adapt_sha: Optional[str] = None
    exec_profile_id: Optional[str] = None
    tool_contract_digest: Optional[str] = None
    prompt_template_digest: Optional[str] = None
    runtime_kind: Optional[str] = None
    runtime_version: Optional[str] = None

    if unit.arm == "mm_single":
        (
            proj_cfg_path,
            proj_sha,
            adapt_cfg_path,
            adapt_sha,
        ) = prepare_candidate_runtime(
            cand, local_adapter_context, trial_sup, config_path=config_path
        )
        resolved_ctx = HostAdapter.resolve_adapter_context(
            workspace=str(trial_sup),
            state_dir=str(trial_sup),
            tool_signatures=_get_mcp_tool_signatures(),
            contract_version=MCP_TOOL_CONTRACT_VERSION,
        )
        exec_profile_id = resolved_ctx.execution_profile.profile_id
        tool_contract_digest = (
            resolved_ctx.execution_profile.tool_contract_digest
        )
        prompt_template_digest = (
            resolved_ctx.execution_profile.prompt_template_digest
        )
        runtime_kind = resolved_ctx.execution_profile.runtime_kind
        runtime_version = resolved_ctx.execution_profile.runtime_version

    task_json = json.loads(task_file_path.read_text(encoding="utf-8"))

    capture = CaptureOllamaUsage(
        output_dir=output_dir,
        trial_id=unit.trial_id,
    )

    t_wall_start = time.monotonic()
    primary_exception: Optional[Exception] = None
    execution_stage: Optional[str] = None

    if unit.arm == "control_once":
        prompt = build_bare_prompt(task_json)
        t_gen_start = time.monotonic()
        raw_text: Optional[str] = None
        gen_exc: Optional[Exception] = None
        try:
            raw_text, meta = request_control_generation(
                prompt=prompt,
                model=cand.model_tag,
                host=ollama_host,
                timeout_sec=120,
            )
            t_gen_dur = time.monotonic() - t_gen_start
            capture.record_generation(
                phase="control",
                model=cand.model_tag,
                provider="ollama",
                temperature=0.2,
                max_tokens=4000,
                prompt_tokens=meta.get("prompt_tokens"),
                completion_tokens=meta.get("completion_tokens"),
                total_tokens=meta.get("total_tokens"),
                latency_seconds=t_gen_dur,
                raw_response_text=raw_text,
            )
        except Exception as exc:
            t_gen_dur = time.monotonic() - t_gen_start
            capture.generation_calls += 1
            capture.events.append({
                "phase": "control",
                "model": cand.model_tag,
                "provider": "ollama",
                "prompt_tokens": None,
                "completion_tokens": None,
                "total_tokens": None,
                "latency_seconds": t_gen_dur,
                "raw_response_relpath": None,
                "raw_response_sha256": None,
                "error": str(exc),
            })
            gen_exc = exc
            primary_exception = exc
            execution_stage = "generation"

        if gen_exc is None and raw_text is not None:
            try:
                _apply_response(
                    ResponseApplicationRequest(
                        raw_response=raw_text,
                        policy=ResponseApplicationPolicy(
                            workspace_root=str(trial_ws),
                        ),
                    )
                )
            except Exception as exc:
                primary_exception = exc
                exc_s = str(exc).lower()
                if any(
                    k in exc_s
                    for k in (
                        "schema",
                        "ambiguous",
                        "no valid file",
                        "xml leakage",
                        "oversized",
                        "parse",
                    )
                ):
                    execution_stage = "schema"
                else:
                    execution_stage = "application"

    elif unit.arm == "mm_single":
        adapter = HostAdapter()
        sigs = _get_mcp_tool_signatures()
        with capture:
            try:
                adapter.solve(
                    workspace=str(trial_ws),
                    p_cfg_path=str(proj_cfg_path),
                    task_input=str(task_file_path.resolve()),
                    state_dir=str(trial_sup),
                    tool_signatures=sigs,
                    contract_version=MCP_TOOL_CONTRACT_VERSION,
                    temperature=0.2,
                )
            except Exception as exc:
                primary_exception = exc
                exc_s = str(exc).lower()
                if isinstance(exc, TimeoutError) or "timeout" in exc_s:
                    execution_stage = "generation"
                elif any(
                    k in exc_s
                    for k in (
                        "generate",
                        "ollama",
                        "connection refused",
                        "connection reset",
                        "timed out",
                    )
                ) or isinstance(exc, (urllib.error.URLError, ConnectionError)):
                    execution_stage = "generation"
                elif any(
                    k in exc_s
                    for k in (
                        "schema",
                        "ambiguous",
                        "no valid file",
                        "xml leakage",
                        "oversized",
                        "parse",
                    )
                ):
                    execution_stage = "schema"
                else:
                    execution_stage = "application"

    output_files = sorted(
        str(p.relative_to(trial_ws))
        for p in trial_ws.rglob("*")
        if p.is_file() and not p.name.startswith(".")
    )

    verifier_completed = False
    passed = False
    failure_category: Optional[str] = None
    verifier_payload: Optional[Dict[str, Any]] = None
    infra_error = False

    has_incomplete_attempt = any(
        e.get("prompt_tokens") is None or e.get("completion_tokens") is None
        for e in capture.events
    )
    if capture.events:
        token_cov = not has_incomplete_attempt
    else:
        token_cov = (
            primary_exception is not None
            and execution_stage in ("schema", "application")
        )

    if primary_exception is not None:
        exc_str = str(primary_exception).lower()
        if execution_stage == "generation":
            infra_error = True
            if (
                isinstance(primary_exception, TimeoutError)
                or "timed out" in exc_str
            ):
                failure_category = "timeout"
            else:
                failure_category = "generation_error"
        elif execution_stage == "schema":
            infra_error = False
            failure_category = "response_schema_error"
        else:
            infra_error = False
            failure_category = classify_failure(
                None, exception=primary_exception, stage="application"
            )
            if not failure_category:
                failure_category = "application_error"

        if not infra_error and trial_ws.is_dir():
            try:
                v_res = verify_task(task_json, workspace=str(trial_ws))
                if (
                    isinstance(v_res, dict)
                    and v_res.get("status") in ("success", "fail")
                ):
                    verifier_completed = True
                    verifier_payload = v_res
                else:
                    verifier_completed = False
                    infra_error = True
                    failure_category = "verifier_error"
                    verifier_payload = (
                        v_res
                        if isinstance(v_res, dict)
                        else {"error": "Invalid verifier output"}
                    )
            except Exception as exc:
                verifier_completed = False
                infra_error = True
                failure_category = "verifier_error"
                verifier_payload = {"error": str(exc)}
            passed = False
    else:
        try:
            v_res = verify_task(task_json, workspace=str(trial_ws))
            if (
                isinstance(v_res, dict)
                and v_res.get("status") in ("success", "fail")
            ):
                verifier_completed = True
                verifier_payload = v_res
                passed = v_res.get("status") == "success"
                if not passed:
                    failure_category = classify_failure(v_res)
            else:
                infra_error = True
                verifier_completed = False
                failure_category = "verifier_error"
                verifier_payload = (
                    v_res
                    if isinstance(v_res, dict)
                    else {"error": "Invalid verifier output"}
                )
        except Exception as exc:
            infra_error = True
            verifier_completed = False
            failure_category = "verifier_error"
            verifier_payload = {"error": str(exc)}

    if (
        has_incomplete_attempt
        or (not token_cov and execution_stage == "generation")
    ):
        infra_error = True
        passed = False
        if failure_category is None:
            failure_category = "generation_error"

    wall_lat = round(time.monotonic() - t_wall_start, 4)

    prompt_toks = (
        sum(e["prompt_tokens"] for e in capture.events)
        if token_cov
        else None
    )
    comp_toks = (
        sum(e["completion_tokens"] for e in capture.events)
        if token_cov
        else None
    )
    tot_toks = (
        prompt_toks + comp_toks
        if prompt_toks is not None and comp_toks is not None
        else None
    )
    mod_lat = (
        sum(e.get("latency_seconds", 0.0) for e in capture.events)
        if capture.events
        else None
    )

    raw_relpaths = [
        e["raw_response_relpath"]
        for e in capture.events
        if e.get("raw_response_relpath")
    ]
    raw_shas = [
        e["raw_response_sha256"]
        for e in capture.events
        if e.get("raw_response_sha256")
    ]

    expected_unit_base = unit_exec_base or expected_exec_base
    prov_complete = (
        M13_EXPERIMENT_BASE_SHA == unit.experiment_base_sha
        and expected_exec_base == expected_unit_base
        and bool(harness_sha)
        and bool(unit.candidate_id)
        and bool(unit.model_tag)
        and bool(unit.model_digest)
        and bool(ollama_version)
        and bool(unit.task_id)
        and bool(unit.task_sha256)
        and (
            unit.arm == "control_once"
            or (
                unit.arm == "mm_single"
                and bool(proj_sha)
                and bool(adapt_sha)
                and bool(exec_profile_id)
                and bool(tool_contract_digest)
                and bool(prompt_template_digest)
                and bool(runtime_kind)
                and bool(runtime_version)
                and bool(local_adapter_context.model_class)
            )
        )
    )

    record: Dict[str, Any] = {
        "schema_version": "1.0.0",
        "experiment_id": active_exp_id,
        "trial_id": unit.trial_id,
        "order_index": unit.order_index,
        "experiment_base_sha": M13_EXPERIMENT_BASE_SHA,
        "execution_base_sha": expected_exec_base,
        "harness_sha": harness_sha,
        "candidate_id": unit.candidate_id,
        "arm": unit.arm,
        "replicate": unit.replicate,
        "model_tag": unit.model_tag,
        "model_family": unit.model_family,
        "model_class": unit.model_class,
        "model_digest": unit.model_digest,
        "quantization": unit.quantization,
        "packaged_context": unit.packaged_context,
        "effective_context": M13_EFFECTIVE_CONTEXT_LIMIT,
        "tier": unit.tier,
        "task_id": unit.task_id,
        "task_file": unit.task_file,
        "task_sha256": unit.task_sha256,
        "ollama_version": ollama_version,
        "projected_config_sha256": proj_sha,
        "ephemeral_adapter_config_sha256": adapt_sha,
        "execution_profile_id": exec_profile_id,
        "tool_contract_digest": tool_contract_digest,
        "prompt_template_digest": prompt_template_digest,
        "runtime_kind": runtime_kind,
        "runtime_version": runtime_version,
        "runtime_model_class": (
            local_adapter_context.model_class
            if unit.arm == "mm_single"
            else None
        ),
        "execution_base_to_harness_changed_paths": changed_paths,
        "generation_call_count": capture.generation_calls,
        "output_paths": output_files,
        "swarm_enabled": False,
        "recovery_enabled": False,
        "recovery_attempted": False,
        "verifier_completed": verifier_completed,
        "passed": passed,
        "failure_category": failure_category,
        "verifier_payload": verifier_payload,
        "prompt_tokens": prompt_toks,
        "completion_tokens": comp_toks,
        "total_tokens": tot_toks,
        "model_latency_seconds": mod_lat,
        "wall_latency_seconds": wall_lat,
        "provenance_complete": prov_complete,
        "token_coverage_complete": token_cov,
        "infrastructure_error": infra_error,
        "trace_artifact_relpath": None,
        "trace_artifact_sha256": None,
        "raw_response_relpaths": raw_relpaths,
        "raw_response_sha256s": raw_shas,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    validate_payload_against_schema(record, "trial_record", contract_path)
    return record


def execute_cross_model_plan(
    plan: Optional[Any] = None,
    *,
    output_dir: Optional[Path] = None,
    workspace_root: Optional[Path] = None,
    support_root: Optional[Path] = None,
    config_path: Path = DEFAULT_CONFIG_PATH,
    contract_path: Path = DEFAULT_CONTRACT_PATH,
    lock_path: Path = LOCK_FILE_PATH,
    dry_run: bool = False,
    harness_sha: Optional[str] = None,
    local_adapter_context: Optional[AdapterRuntimeContext] = None,
    ollama_host: str = DEFAULT_OLLAMA_HOST,
    experiment_id: str = M13_EXPERIMENT_ID,
) -> Dict[str, Any]:
    """Execute complete cross-model plan under SingleInstanceLock."""
    if harness_sha is None:
        harness_sha = get_current_git_sha()

    if plan is None:
        plan = materialize_execution_plan(
            harness_sha=harness_sha,
            config_path=config_path,
            experiment_id=experiment_id,
        )

    exp_id = (
        plan.get("experiment_id")
        if isinstance(plan, dict)
        else getattr(plan, "experiment_id", experiment_id)
    )
    if not exp_id:
        exp_id = experiment_id

    if exp_id == M13_PHASE_B_EXPERIMENT_ID:
        exec_base = M13_PHASE_B_EXECUTION_BASE_SHA
    elif exp_id == M13_EXPERIMENT_ID:
        exec_base = M13_EXECUTION_BASE_SHA
    else:
        raise ValueError(f"Unsupported experiment_id: {exp_id}")

    if not dry_run:
        if output_dir is not None and output_dir.exists():
            raise FileExistsError(
                f"Live output directory already exists: {output_dir}"
            )
        if workspace_root is not None and workspace_root.exists():
            raise FileExistsError(
                f"Live workspace root already exists: {workspace_root}"
            )

    changed_paths = verify_base_to_harness_delta(
        exec_base, harness_sha
    )

    with SingleInstanceLock(lock_path):
        plan_validation = validate_execution_plan(
            plan, contract_path=contract_path, current_head=harness_sha
        )
        if not plan_validation["valid"]:
            raise ValueError(
                f"Execution plan validation failed: "
                f"{plan_validation['errors']}"
            )

        preflight = run_preflight(
            config_path=config_path,
            contract_path=contract_path,
            lock_already_held=True,
            experiment_id=exp_id,
        )
        if preflight["status"] != "PASSED":
            raise RuntimeError(
                f"Preflight check failed before execution: "
                f"{preflight['blocking_reasons']}"
            )

        observed_ollama_ver = preflight.get("ollama_version")
        if not observed_ollama_ver or observed_ollama_ver == "unknown":
            raise RuntimeError(
                "Preflight check did not observe a valid Ollama version"
            )

        sigs = _get_mcp_tool_signatures()
        if local_adapter_context is not None:
            local_ctx = local_adapter_context
        else:
            canonical_adapter = Path(".mighty-mouse") / ADAPTER_CONFIG_FILENAME
            if not canonical_adapter.is_file():
                raise FileNotFoundError(
                    f"Canonical MCP adapter identity is not configured: "
                    f"{canonical_adapter}; run setup_workspace"
                )
            local_ctx = HostAdapter.resolve_adapter_context(
                ".",
                state_dir=".mighty-mouse",
                tool_signatures=sigs,
                contract_version=MCP_TOOL_CONTRACT_VERSION,
            )

        trial_units = [
            CrossModelPlanUnit(**u) if isinstance(u, dict) else u
            for u in (
                plan.get("trial_units", [])
                if isinstance(plan, dict)
                else plan
            )
        ]

        if dry_run:
            with tempfile.TemporaryDirectory() as dry_tmp:
                dry_support = Path(dry_tmp)
                for cand in FROZEN_CANDIDATES.values():
                    prepare_candidate_runtime(
                        cand,
                        local_ctx,
                        dry_support / cand.candidate_id,
                        config_path=config_path,
                    )

            dry_summary: Dict[str, Any] = {
                "schema_version": "1.0.0",
                "experiment_id": exp_id,
                "experiment_base_sha": plan.get(
                    "experiment_base_sha", M13_EXPERIMENT_BASE_SHA
                ) if isinstance(plan, dict) else getattr(
                    plan, "experiment_base_sha", M13_EXPERIMENT_BASE_SHA
                ),
                "execution_base_sha": exec_base,
                "harness_sha": harness_sha,
                "execution_base_to_harness_changed_paths": changed_paths,
                "planned_trial_count": len(trial_units),
                "executed_trial_count": 0,
                "status": "dry_run",
                "stop_reason": None,
                "generation_calls": 0,
                "total_tokens": None,
                "total_analyzable": 0,
                "total_passed": 0,
                "total_infrastructure_excluded": 0,
                "aggregates_by_candidate": {
                    cid: {
                        "executed": 0,
                        "passed": 0,
                        "analyzable": 0,
                        "infrastructure_excluded": 0,
                        "generation_calls": 0,
                        "total_tokens": 0,
                    }
                    for cid in FROZEN_CANDIDATES
                },
                "aggregates_by_arm": {
                    arm: {
                        "executed": 0,
                        "passed": 0,
                        "analyzable": 0,
                        "infrastructure_excluded": 0,
                        "generation_calls": 0,
                        "total_tokens": 0,
                    }
                    for arm in ("control_once", "mm_single")
                },
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            validate_payload_against_schema(
                dry_summary, "run_summary", contract_path
            )
            if output_dir is not None:
                output_dir.mkdir(parents=True, exist_ok=True)
                _atomic_write_json(
                    output_dir / "run_summary.json",
                    dry_summary,
                    allow_overwrite=True,
                )
            return dry_summary

        if output_dir is None:
            raise ValueError("output_dir must be provided for live run")
        if workspace_root is None:
            raise ValueError("workspace_root must be provided for live run")
        if support_root is None:
            support_root = workspace_root / "support"

        output_dir.mkdir(parents=True, exist_ok=False)
        trials_dir = output_dir / "trials"
        trials_dir.mkdir(parents=True, exist_ok=True)

        trial_records: List[Dict[str, Any]] = []
        stop_reason: Optional[str] = None
        status = "completed"

        for unit in trial_units:
            cand = FROZEN_CANDIDATES[unit.candidate_id]
            try:
                current_digest = HostAdapter.resolve_ollama_model_digest(
                    cand.model_tag
                )
            except Exception as exc:
                stop_reason = (
                    f"Model digest resolution failed before trial "
                    f"{unit.trial_id}: {exc}"
                )
                status = "aborted"
                break

            if current_digest != cand.model_digest:
                stop_reason = (
                    f"Model digest changed before trial {unit.trial_id}: "
                    f"{current_digest} != {cand.model_digest}"
                )
                status = "aborted"
                break

            try:
                current_ver = query_ollama_version(host=ollama_host)
            except Exception as exc:
                stop_reason = (
                    f"Ollama version query failed before trial "
                    f"{unit.trial_id}: {exc}"
                )
                status = "aborted"
                break

            if current_ver != observed_ollama_ver:
                stop_reason = (
                    f"Ollama version drift detected before trial "
                    f"{unit.trial_id}: preflight was '{observed_ollama_ver}', "
                    f"observed '{current_ver}'"
                )
                status = "aborted"
                break

            try:
                record = execute_trial_unit(
                    unit,
                    workspace_root=workspace_root,
                    support_root=support_root,
                    output_dir=output_dir,
                    local_adapter_context=local_ctx,
                    config_path=config_path,
                    contract_path=contract_path,
                    harness_sha=harness_sha,
                    ollama_version=observed_ollama_ver,
                    ollama_host=ollama_host,
                    experiment_id=exp_id,
                    execution_base_sha=exec_base,
                )
            except Exception as exc:
                stop_reason = (
                    f"Unhandled execution exception in trial {unit.trial_id}: "
                    f"{exc}"
                )
                status = "aborted"
                break

            trial_records.append(record)
            t_path = trials_dir / f"{unit.trial_id}.json"
            _atomic_write_json(t_path, record, allow_overwrite=False)

            if record.get("infrastructure_error"):
                stop_reason = (
                    f"Infrastructure error encountered in trial "
                    f"{unit.trial_id}: {record.get('failure_category')}"
                )
                status = "aborted"
                break

            if not record.get("provenance_complete"):
                stop_reason = (
                    f"Provenance incomplete in trial {unit.trial_id}"
                )
                status = "aborted"
                break

            if not record.get("token_coverage_complete"):
                stop_reason = (
                    f"Token coverage incomplete in trial {unit.trial_id}"
                )
                status = "aborted"
                break

        total_gens = sum(r["generation_call_count"] for r in trial_records)

        def _is_analyzable(r: Dict[str, Any]) -> bool:
            return (
                not r.get("infrastructure_error")
                and bool(r.get("token_coverage_complete"))
                and r.get("failure_category") not in (
                    "verifier_error", "generation_error", "timeout"
                )
            )

        def _is_infra_excluded(r: Dict[str, Any]) -> bool:
            return (
                bool(r.get("infrastructure_error"))
                or not bool(r.get("token_coverage_complete"))
                or r.get("failure_category") in (
                    "verifier_error", "generation_error", "timeout"
                )
            )

        cand_aggs: Dict[str, Any] = {}
        for cid in FROZEN_CANDIDATES:
            c_recs = [r for r in trial_records if r["candidate_id"] == cid]
            c_all_cov = bool(c_recs) and all(
                r.get("token_coverage_complete")
                and r.get("total_tokens") is not None
                for r in c_recs
            )
            cand_aggs[cid] = {
                "executed": len(c_recs),
                "passed": sum(1 for r in c_recs if r["passed"]),
                "analyzable": sum(1 for r in c_recs if _is_analyzable(r)),
                "infrastructure_excluded": sum(
                    1 for r in c_recs if _is_infra_excluded(r)
                ),
                "generation_calls": sum(
                    r["generation_call_count"] for r in c_recs
                ),
                "total_tokens": (
                    sum(r["total_tokens"] for r in c_recs)
                    if c_all_cov
                    else (0 if not c_recs else None)
                ),
            }

        arm_aggs: Dict[str, Any] = {}
        for arm in ("control_once", "mm_single"):
            a_recs = [r for r in trial_records if r["arm"] == arm]
            a_all_cov = bool(a_recs) and all(
                r.get("token_coverage_complete")
                and r.get("total_tokens") is not None
                for r in a_recs
            )
            arm_aggs[arm] = {
                "executed": len(a_recs),
                "passed": sum(1 for r in a_recs if r["passed"]),
                "analyzable": sum(1 for r in a_recs if _is_analyzable(r)),
                "infrastructure_excluded": sum(
                    1 for r in a_recs if _is_infra_excluded(r)
                ),
                "generation_calls": sum(
                    r["generation_call_count"] for r in a_recs
                ),
                "total_tokens": (
                    sum(r["total_tokens"] for r in a_recs)
                    if a_all_cov
                    else (0 if not a_recs else None)
                ),
            }

        all_cov = bool(trial_records) and all(
            r.get("token_coverage_complete")
            and r.get("total_tokens") is not None
            for r in trial_records
        )
        sum_tokens = (
            sum(r["total_tokens"] for r in trial_records)
            if all_cov
            else (0 if not trial_records else None)
        )

        summary: Dict[str, Any] = {
            "schema_version": "1.0.0",
            "experiment_id": exp_id,
            "experiment_base_sha": plan.get(
                "experiment_base_sha", M13_EXPERIMENT_BASE_SHA
            ) if isinstance(plan, dict) else getattr(
                plan, "experiment_base_sha", M13_EXPERIMENT_BASE_SHA
            ),
            "execution_base_sha": exec_base,
            "harness_sha": harness_sha,
            "execution_base_to_harness_changed_paths": changed_paths,
            "planned_trial_count": len(trial_units),
            "executed_trial_count": len(trial_records),
            "status": status,
            "stop_reason": stop_reason,
            "generation_calls": total_gens,
            "total_tokens": sum_tokens,
            "total_analyzable": sum(
                1 for r in trial_records if _is_analyzable(r)
            ),
            "total_passed": sum(1 for r in trial_records if r["passed"]),
            "total_infrastructure_excluded": sum(
                1 for r in trial_records if _is_infra_excluded(r)
            ),
            "aggregates_by_candidate": cand_aggs,
            "aggregates_by_arm": arm_aggs,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        validate_payload_against_schema(
            summary, "run_summary", contract_path
        )
        _atomic_write_json(
            output_dir / "run_summary.json", summary, allow_overwrite=False
        )
        return summary
