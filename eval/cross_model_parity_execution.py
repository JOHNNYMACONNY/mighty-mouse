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
from pathlib import Path
import tempfile
import time
from typing import Any, Dict, List, Optional, Tuple
import yaml

from eval.cross_model_parity import (
    DEFAULT_CONFIG_PATH,
    DEFAULT_CONTRACT_PATH,
    FROZEN_ANCHOR_TASKS,
    FROZEN_CANDIDATES,
    LOCK_FILE_PATH,
    M13_EFFECTIVE_CONTEXT_LIMIT,
    M13_EXECUTION_BASE_SHA,
    M13_EXPERIMENT_BASE_SHA,
    M13_EXPERIMENT_ID,
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
    serialized_adapter = json.dumps(adapter_cfg, indent=2, sort_keys=True)
    adapter_cfg_path.write_text(serialized_adapter + "\n", encoding="utf-8")
    adapter_sha = hashlib.sha256(
        serialized_adapter.encode("utf-8")
    ).hexdigest()

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
) -> Dict[str, Any]:
    """Execute one cross-model trial unit with verification."""
    if isinstance(unit, dict):
        unit = CrossModelPlanUnit(**unit)

    if harness_sha is None:
        harness_sha = get_current_git_sha()

    cand = FROZEN_CANDIDATES.get(unit.candidate_id)
    if cand is None:
        raise ValueError(f"Unknown candidate {unit.candidate_id}")
    task_def = FROZEN_ANCHOR_TASKS.get(unit.task_id)
    if task_def is None:
        raise ValueError(f"Unknown anchor task {unit.task_id}")

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
        M13_EXECUTION_BASE_SHA, harness_sha
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
    applied_files: List[str] = []

    if unit.arm == "control_once":
        instructions = task_json.get("instructions", "")
        prompt = (
            f"Solve the following coding task:\n\n{instructions}\n\n"
            f"Provide full code in valid diff or file blocks."
        )
        t_gen_start = time.monotonic()
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
            applied = _apply_response(
                ResponseApplicationRequest(
                    raw_response=raw_text,
                    policy=ResponseApplicationPolicy(
                        workspace_root=str(trial_ws),
                    ),
                )
            )
            applied_files = [str(f) for f in applied]
        except Exception as exc:
            primary_exception = exc

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

    verifier_completed = False
    passed = False
    failure_category: Optional[str] = None
    verifier_payload: Optional[Dict[str, Any]] = None
    infra_error = False

    if primary_exception is not None:
        failure_category = classify_failure(None, exception=primary_exception)
        if failure_category in ("generation_error", "timeout"):
            infra_error = True
    else:
        try:
            v_res = verify_task(task_json, workspace=str(trial_ws))
            verifier_completed = True
            if isinstance(v_res, dict):
                verifier_payload = v_res
                passed = v_res.get("status") == "success"
                if not passed:
                    failure_category = classify_failure(v_res)
            else:
                infra_error = True
                failure_category = "verifier_error"
        except Exception as exc:
            infra_error = True
            failure_category = "verifier_error"
            verifier_payload = {"error": str(exc)}

    wall_lat = round(time.monotonic() - t_wall_start, 4)

    prompt_toks = (
        sum(
            e["prompt_tokens"]
            for e in capture.events
            if e.get("prompt_tokens") is not None
        )
        if capture.events
        else None
    )
    comp_toks = (
        sum(
            e["completion_tokens"]
            for e in capture.events
            if e.get("completion_tokens") is not None
        )
        if capture.events
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

    record: Dict[str, Any] = {
        "schema_version": "1.0.0",
        "experiment_id": M13_EXPERIMENT_ID,
        "trial_id": unit.trial_id,
        "order_index": unit.order_index,
        "experiment_base_sha": M13_EXPERIMENT_BASE_SHA,
        "execution_base_sha": M13_EXECUTION_BASE_SHA,
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
        "ollama_version": "0.33.2",
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
        "output_paths": applied_files,
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
        "provenance_complete": True,
        "token_coverage_complete": capture.token_coverage_complete,
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
    plan: Optional[List[CrossModelPlanUnit]] = None,
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
) -> Dict[str, Any]:
    """Execute complete cross-model plan under SingleInstanceLock."""
    if harness_sha is None:
        harness_sha = get_current_git_sha()

    if plan is None:
        plan = materialize_execution_plan(
            harness_sha=harness_sha, config_path=config_path
        )

    if not dry_run and output_dir is not None:
        if output_dir.exists():
            raise FileExistsError(
                f"Live output directory already exists: {output_dir}"
            )

    changed_paths = verify_base_to_harness_delta(
        M13_EXECUTION_BASE_SHA, harness_sha
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
        )
        if preflight["status"] != "PASSED":
            raise RuntimeError(
                f"Preflight check failed before execution: "
                f"{preflight['blocking_reasons']}"
            )

        sigs = _get_mcp_tool_signatures()
        if local_adapter_context is not None:
            local_ctx = local_adapter_context
        elif (Path(".mighty-mouse") / ADAPTER_CONFIG_FILENAME).is_file():
            local_ctx = HostAdapter.resolve_adapter_context(
                ".", state_dir=".mighty-mouse", tool_signatures=sigs,
                contract_version=MCP_TOOL_CONTRACT_VERSION
            )
        else:
            fb_tmp = tempfile.mkdtemp()
            fb_state = Path(fb_tmp) / ".mighty-mouse"
            fb_state.mkdir(parents=True, exist_ok=True)
            cfg = HostAdapter.build_adapter_config(
                repository="JOHNNYMACONNY/mighty-mouse",
                model_digest="sha256:" + "0" * 64,
                model_class="local-small",
                effective_context_limit=8192,
                runtime_kind="antigravity",
                runtime_version="1.0.0",
                ollama_model=None,
                tool_signatures=sigs,
                contract_version=MCP_TOOL_CONTRACT_VERSION,
            )
            (fb_state / ADAPTER_CONFIG_FILENAME).write_text(
                json.dumps(cfg), encoding="utf-8"
            )
            local_ctx = HostAdapter.resolve_adapter_context(
                fb_tmp,
                state_dir=str(fb_state),
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
                        cand, local_ctx, dry_support / cand.candidate_id,
                        config_path=config_path
                    )

            dry_summary: Dict[str, Any] = {
                "schema_version": "1.0.0",
                "experiment_id": M13_EXPERIMENT_ID,
                "experiment_base_sha": M13_EXPERIMENT_BASE_SHA,
                "execution_base_sha": M13_EXECUTION_BASE_SHA,
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
                (output_dir / "run_summary.json").write_text(
                    json.dumps(dry_summary, indent=2) + "\n", encoding="utf-8"
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
            current_digest = HostAdapter.resolve_ollama_model_digest(
                cand.model_tag
            )
            if current_digest != cand.model_digest:
                stop_reason = (
                    f"Model digest changed before trial {unit.trial_id}: "
                    f"{current_digest} != {cand.model_digest}"
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
            t_path.write_text(
                json.dumps(record, indent=2) + "\n", encoding="utf-8"
            )

            if record.get("infrastructure_error"):
                stop_reason = (
                    f"Infrastructure error encountered in trial "
                    f"{unit.trial_id}: {record.get('failure_category')}"
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
        token_vals = [
            r["total_tokens"]
            for r in trial_records
            if r["total_tokens"] is not None
        ]
        sum_tokens = (
            sum(token_vals) if len(token_vals) == len(trial_records) else None
        )

        cand_aggs: Dict[str, Any] = {}
        for cid in FROZEN_CANDIDATES:
            c_recs = [r for r in trial_records if r["candidate_id"] == cid]
            cand_aggs[cid] = {
                "executed": len(c_recs),
                "passed": sum(1 for r in c_recs if r["passed"]),
                "analyzable": sum(
                    1 for r in c_recs if not r["infrastructure_error"]
                ),
                "infrastructure_excluded": sum(
                    1 for r in c_recs if r["infrastructure_error"]
                ),
                "generation_calls": sum(
                    r["generation_call_count"] for r in c_recs
                ),
                "total_tokens": sum(
                    r["total_tokens"] or 0 for r in c_recs
                ),
            }

        arm_aggs: Dict[str, Any] = {}
        for arm in ("control_once", "mm_single"):
            a_recs = [r for r in trial_records if r["arm"] == arm]
            arm_aggs[arm] = {
                "executed": len(a_recs),
                "passed": sum(1 for r in a_recs if r["passed"]),
                "analyzable": sum(
                    1 for r in a_recs if not r["infrastructure_error"]
                ),
                "infrastructure_excluded": sum(
                    1 for r in a_recs if r["infrastructure_error"]
                ),
                "generation_calls": sum(
                    r["generation_call_count"] for r in a_recs
                ),
                "total_tokens": sum(
                    r["total_tokens"] or 0 for r in a_recs
                ),
            }

        summary: Dict[str, Any] = {
            "schema_version": "1.0.0",
            "experiment_id": M13_EXPERIMENT_ID,
            "experiment_base_sha": M13_EXPERIMENT_BASE_SHA,
            "execution_base_sha": M13_EXECUTION_BASE_SHA,
            "harness_sha": harness_sha,
            "execution_base_to_harness_changed_paths": changed_paths,
            "planned_trial_count": len(trial_units),
            "executed_trial_count": len(trial_records),
            "status": status,
            "stop_reason": stop_reason,
            "generation_calls": total_gens,
            "total_tokens": sum_tokens,
            "total_analyzable": sum(
                1 for r in trial_records if not r["infrastructure_error"]
            ),
            "total_passed": sum(1 for r in trial_records if r["passed"]),
            "total_infrastructure_excluded": sum(
                1 for r in trial_records if r["infrastructure_error"]
            ),
            "aggregates_by_candidate": cand_aggs,
            "aggregates_by_arm": arm_aggs,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        validate_payload_against_schema(
            summary, "run_summary", contract_path
        )
        (output_dir / "run_summary.json").write_text(
            json.dumps(summary, indent=2) + "\n", encoding="utf-8"
        )
        return summary
