"""Mighty Mouse MCP stdio server."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
import secrets
from typing import Any, Sequence

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    class FastMCP:  # type: ignore[no-redef]
        def __init__(self, name: str) -> None:
            self.name = name

        def tool(self, *args: Any, **kwargs: Any) -> Any:
            def decorator(func: Any) -> Any:
                return func
            return decorator

        def run(self, *args: Any, **kwargs: Any) -> None:
            pass

from mighty_mouse.host.adapter import (
    ADAPTER_CONFIG_FILENAME,
    MCP_TOOL_CONTRACT_VERSION,
    HostAdapter,
)
from mighty_mouse.protocols import PROTOCOL_VERSION, get_protocol
from mighty_mouse.v2.engine import PolicyEngine
from mighty_mouse.v2.foundation import (
    ComputeScalingPin,
    ComputeScalingPolicy,
    HybridHandoff,
    ImmutableStateStore,
    Mode,
    Pin,
    Preview,
    Scope,
    TaskCategory,
)
from mighty_mouse.v2.runtime import AutopilotRunRequest, run_autopilot
from mighty_mouse.v2.signals import SignalLifecycle
from mighty_mouse.v2.telemetry import SignalTelemetry
from mighty_mouse.verifier import verify as verify_workspace

mcp = FastMCP("mighty-mouse")


def run_verify(
    workspace: str,
    test_command: str | None = None,
    lint_command: str | None = None,
    build_command: str | None = None,
    allowed_paths: list[str] | None = None,
    timeout_sec: int = 120,
) -> dict:
    """Run project tests, lint, build, and optional Git scope checks."""
    return verify_workspace(
        workspace=workspace,
        test_command=test_command,
        lint_command=lint_command,
        build_command=build_command,
        allowed_paths=allowed_paths,
        timeout_sec=timeout_sec,
    ).to_dict()


def run_protocol(task_description: str, complexity: str = "medium") -> dict[str, str]:
    """Return the versioned protocol appropriate for a task's complexity."""
    if not task_description.strip():
        raise ValueError("task_description must not be empty")
    prompt = get_protocol(complexity=complexity)
    return {
        "protocol_version": PROTOCOL_VERSION,
        "complexity": complexity.lower().strip(),
        "task_description": task_description.strip(),
        "protocol_prompt": prompt,
        "verification_reminder": (
            "After editing, call mighty-mouse/verify_and_record. Fix failures and retry up to three rounds."
        ),
    }


def _verifier_category(result: dict) -> str:
    checks = result["checks"]
    selected = next((check for check in checks if not check["passed"]), checks[0] if checks else None)
    if selected is None:
        return "none"
    return {"tests": "tests", "lint": "lint", "build": "build", "scope": "manual"}.get(selected["name"], "manual")


def _get_mcp_tool_signatures() -> dict:
    return {
        "protocol": run_protocol,
        "verify": run_verify,
        "setup_workspace": run_setup_workspace,
        "verify_and_record": run_verify_and_record,
        "recording_audit": run_recording_audit,
        "run": run_run,
        "agent_execute": run_agent_execute,
        "swarm_execute": run_swarm_execute,
        "policy_status": run_policy_status,
        "policy_preview": run_policy_preview,
        "policy_pin": run_policy_pin,
        "policy_rollback": run_policy_rollback,
        "compute_scaling_status": run_compute_scaling_status,
        "compute_scaling_preview": run_compute_scaling_preview,
        "compute_scaling_pin": run_compute_scaling_pin,
    }


def _mcp_tool_contract() -> dict[str, str]:
    return HostAdapter.get_tool_contract(_get_mcp_tool_signatures(), contract_version=MCP_TOOL_CONTRACT_VERSION)


def _adapter_scope(workspace: str, state_dir: str | None, task_category: str) -> tuple[Path, Scope, str, str]:
    return HostAdapter.resolve_adapter_scope(
        workspace, state_dir, task_category,
        tool_signatures=_get_mcp_tool_signatures(),
        contract_version=MCP_TOOL_CONTRACT_VERSION,
    )


def _ollama_model_digest(model: str) -> str:
    return HostAdapter.resolve_ollama_model_digest(model)


def _current_execution_profile(*, runtime_kind: str, runtime_version: str, effective_context_limit: int):
    return HostAdapter.build_execution_profile(
        runtime_kind=runtime_kind,
        runtime_version=runtime_version,
        effective_context_limit=effective_context_limit,
        tool_signatures=_get_mcp_tool_signatures(),
        contract_version=MCP_TOOL_CONTRACT_VERSION,
    )


def _adapter_config(
    *, repository: str, model_digest: str, model_class: str, effective_context_limit: int,
    runtime_kind: str, runtime_version: str, ollama_model: str | None,
) -> dict[str, str | int]:
    return HostAdapter.build_adapter_config(
        repository=repository,
        model_digest=model_digest,
        model_class=model_class,
        effective_context_limit=effective_context_limit,
        runtime_kind=runtime_kind,
        runtime_version=runtime_version,
        ollama_model=ollama_model,
        tool_signatures=_get_mcp_tool_signatures(),
        contract_version=MCP_TOOL_CONTRACT_VERSION,
    )


def _adapter_scope_from_config(config: dict[str, Any]) -> Scope:
    return HostAdapter.validate_adapter_config(
        config,
        tool_signatures=_get_mcp_tool_signatures(),
        contract_version=MCP_TOOL_CONTRACT_VERSION,
    )


def run_setup_workspace(
    workspace: str, repository: str, *, ollama_model: str | None = None,
    model_digest: str | None = None, model_class: str = "unknown", effective_context_limit: int = 8192,
    runtime_kind: str, runtime_version: str, replace: bool = False,
) -> dict[str, str | bool]:
    """Pin a host's exact identity needed for automatic Signal collection."""
    workspace_path = Path(workspace)
    if not workspace_path.is_dir():
        raise ValueError(f"Workspace is not a directory: {workspace}")
    if (ollama_model is None) == (model_digest is None):
        raise ValueError("Workspace setup requires exactly one of ollama_model or model_digest")
    config = _adapter_config(
        repository=repository, model_digest=_ollama_model_digest(ollama_model) if ollama_model else model_digest,
        model_class=model_class,
        effective_context_limit=effective_context_limit, runtime_kind=runtime_kind, runtime_version=runtime_version,
        ollama_model=ollama_model,
    )
    path = workspace_path / ".mighty-mouse" / ADAPTER_CONFIG_FILENAME
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        if existing == config:
            return {"configured": False, "model_digest": config["model_digest"], "execution_profile_id": config["execution_profile_id"]}
        if not replace:
            raise ValueError("Cline adapter identity is already configured; pass replace=True to update it")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(config, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    temporary.replace(path)
    return {"configured": True, "model_digest": config["model_digest"], "execution_profile_id": config["execution_profile_id"]}


def run_recording_audit(workspace: str, receipt_hash: str, after: str) -> dict[str, bool | int]:
    """Confirm that the exact receipt returned by one task was recorded after it began."""
    normalized_after = after[:-1] + "+00:00" if after.endswith("Z") else after
    threshold = datetime.fromisoformat(normalized_after)
    threshold = threshold.astimezone(timezone.utc) if threshold.tzinfo else threshold.replace(tzinfo=timezone.utc)
    lifecycle = SignalLifecycle(Path(workspace) / ".mighty-mouse")
    count = sum(
        1 for receipt in lifecycle._receipts()
        if receipt["receipt_hash"] == receipt_hash
        and datetime.fromisoformat(receipt["recorded_at"]).astimezone(timezone.utc) >= threshold
    )
    return {"recorded": count > 0, "recent_receipt_count": count}


def run_verify_and_record(
    workspace: str,
    *,
    state_dir: str | None = None,
    task_category: str = "unknown",
    retry_count: int = 0,
    test_command: str | None = None,
    lint_command: str | None = None,
    build_command: str | None = None,
    allowed_paths: list[str] | None = None,
    timeout_sec: int = 120,
) -> dict:
    """Verify a Cline task and persist only its content-free configured v2 Signal."""
    resolved_state_dir, scope, model_digest, execution_profile_id = _adapter_scope(
        workspace, state_dir, task_category
    )
    verification = run_verify(
        workspace, test_command, lint_command, build_command, allowed_paths, timeout_sec
    )
    category = _verifier_category(verification)
    lifecycle = SignalLifecycle(resolved_state_dir)
    telemetry = SignalTelemetry(lifecycle)
    receipt_hash = telemetry.record(
        signal_id=f"signal-{secrets.randbelow(10**30):030d}",
        scope=scope,
        model_digest=model_digest,
        execution_profile_id=execution_profile_id,
        outcome="passed" if verification["passed"] else "failed",
        duration_ms=round(sum(check["duration_sec"] for check in verification["checks"]) * 1000),
        retry_count=retry_count,
        verifier_category=category,
        verifier_result="passed" if verification["passed"] else "failed",
    )
    return {
        "verification": verification,
        "signal_recorded": receipt_hash is not None,
        "receipt_hash": receipt_hash,
    }


def run_run(
    workspace: str,
    *,
    task_category: str = "unknown",
    inferred_mode: str = "coding",
    confidence_percent: int = 100,
    user_mode: str | None = None,
    hybrid_handoff: dict[str, Any] | None = None,
    state_dir: str | None = None,
) -> dict[str, Any]:
    """Select adaptive Mode and Effective Policy for a workspace task using pinned adapter identity."""
    ctx = HostAdapter.resolve_adapter_context(
        workspace,
        state_dir,
        tool_signatures=_get_mcp_tool_signatures(),
        contract_version=MCP_TOOL_CONTRACT_VERSION,
    )
    parsed_task_category = TaskCategory(task_category)
    parsed_inferred_mode = Mode(inferred_mode)
    parsed_user_mode = Mode(user_mode) if user_mode is not None else None

    parsed_handoff: HybridHandoff | None = None
    if hybrid_handoff is not None:
        handoff_scope = Scope(
            mode=Mode.HYBRID,
            repository=ctx.repository,
            task_category=parsed_task_category,
            model_class=ctx.model_class,
        )
        parsed_handoff = HybridHandoff(
            handoff_id=hybrid_handoff["handoff_id"],
            scope=handoff_scope,
            summary=hybrid_handoff["summary"],
            constraints=tuple(hybrid_handoff["constraints"]),
            acceptance_checks=tuple(hybrid_handoff["acceptance_checks"]),
            file_scope=tuple(hybrid_handoff["file_scope"]),
            risks=tuple(hybrid_handoff["risks"]),
        )

    result = run_autopilot(
        AutopilotRunRequest(
            repository=ctx.repository,
            task_category=parsed_task_category,
            model_class=ctx.model_class,
            inferred_mode=parsed_inferred_mode,
            confidence_percent=confidence_percent,
            model_identity=ctx.model_identity,
            execution_profile=ctx.execution_profile,
            user_mode=parsed_user_mode,
            hybrid_handoff=parsed_handoff,
        ),
        ImmutableStateStore(ctx.state_dir),
    )
    return {
        "schema_version": ImmutableStateStore.schema_version,
        "interface": "run",
        "mode": result.mode.value,
        "routing_reason": result.routing_reason,
        "selection": {
            "policy_id": result.selection.policy.policy_id,
            "policy_version": result.selection.policy.version,
            "source": result.selection.source,
            "reason": result.selection.reason,
            "record_hash": result.selection.record_hash,
        },
        "handoff_record_hash": result.handoff_record_hash,
        "routing_record_hash": result.routing_record_hash,
    }


@mcp.tool(name="run")
def run_tool(
    workspace: str,
    task_category: str = "unknown",
    inferred_mode: str = "coding",
    confidence_percent: int = 100,
    user_mode: str | None = None,
    hybrid_handoff: dict[str, Any] | None = None,
    state_dir: str | None = None,
) -> dict[str, Any]:
    """Select adaptive Mode and Effective Policy for a task using pinned workspace identity."""
    return run_run(
        workspace=workspace,
        task_category=task_category,
        inferred_mode=inferred_mode,
        confidence_percent=confidence_percent,
        user_mode=user_mode,
        hybrid_handoff=hybrid_handoff,
        state_dir=state_dir,
    )


def run_agent_execute(
    workspace: str,
    p_cfg_path: str,
    task_input: str,
    *,
    state_dir: str | None = None,
    feedback_str: str | None = None,
    explicit_skills: str | None = None,
    temperature: float | None = None,
    stage: str = "unified",
    plan_file: str | None = None,
) -> dict[str, Any]:
    """Execute canonical agent with compute scaling support."""
    ws_path = Path(workspace)
    if not ws_path.exists() or not ws_path.is_dir():
        raise ValueError(f"workspace directory does not exist: {workspace}")

    cfg_path = Path(p_cfg_path)
    if not cfg_path.exists() or not cfg_path.is_file():
        raise ValueError(f"config file does not exist: {p_cfg_path}")

    task_path = Path(task_input)
    if not task_path.exists() or not task_path.is_file():
        raise ValueError(f"task input file does not exist: {task_input}")

    if stage not in {"unified", "planner", "coder"}:
        raise ValueError(
            f"invalid stage: {stage} (must be unified, planner, or coder)"
        )

    HostAdapter().solve(
        workspace=workspace,
        p_cfg_path=p_cfg_path,
        task_input=task_input,
        state_dir=state_dir,
        tool_signatures=_get_mcp_tool_signatures(),
        contract_version=MCP_TOOL_CONTRACT_VERSION,
        feedback_str=feedback_str,
        explicit_skills=explicit_skills,
        temperature=temperature,
        stage=stage,
        plan_file=plan_file,
    )

    metadata_path = ws_path / "logs" / "last_agent_run.json"
    if not metadata_path.exists():
        raise RuntimeError(
            "Agent run did not produce last_agent_run.json metadata"
        )

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    return {
        "schema_version": 1,
        "interface": "agent_execute",
        "task_id": metadata.get("task_id"),
        "pass_type": metadata.get("pass_type", "clean"),
        "output_files": metadata.get("output_files", []),
        "written_files": metadata.get("written_files", []),
        "deleted_files": metadata.get("deleted_files", []),
        "schema_error": metadata.get("schema_error", False),
        "attempts": metadata.get("attempts", 1),
        "coverage_recovery": {
            "triggered": metadata.get("coverage_recovery_triggered", False),
            "attempts": metadata.get("coverage_recovery_attempts", 0),
            "success": metadata.get("coverage_recovery_success", False),
            "missing_files": metadata.get("coverage_missing_files", []),
            "disallowed_reason": metadata.get(
                "coverage_recovery_disallowed_reason"
            ),
        },
        "compute_scaling": metadata.get("compute_scaling", {}),
    }


@mcp.tool(name="agent_execute")
def agent_execute_tool(
    workspace: str,
    p_cfg_path: str,
    task_input: str,
    state_dir: str | None = None,
    feedback_str: str | None = None,
    explicit_skills: str | None = None,
    temperature: float | None = None,
    stage: str = "unified",
    plan_file: str | None = None,
) -> dict[str, Any]:
    """Execute canonical agent with compute scaling support."""
    return run_agent_execute(
        workspace=workspace,
        p_cfg_path=p_cfg_path,
        task_input=task_input,
        state_dir=state_dir,
        feedback_str=feedback_str,
        explicit_skills=explicit_skills,
        temperature=temperature,
        stage=stage,
        plan_file=plan_file,
    )


def run_swarm_execute(
    workspace: str,
    verification_workspace: str,
    task: dict[str, Any],
    *,
    state_dir: str | None = None,
    concurrency: int = 1,
    test_command: str | Sequence[str] | None = None,
    lint_command: str | Sequence[str] | None = None,
    build_command: str | Sequence[str] | None = None,
    allowed_paths: list[str] | None = None,
    task_config: dict[str, Any] | None = None,
    timeout_sec: int = 120,
) -> dict[str, Any]:
    """Execute task using Multi-Agent Swarm with canonical host provenance."""
    if not isinstance(task, dict):
        raise ValueError("task must be a JSON object / dictionary")
    task_input = json.dumps(task, sort_keys=True)
    solve_result = HostAdapter().solve_swarm(
        workspace=workspace,
        task_input=task_input,
        verification_workspace=verification_workspace,
        state_dir=state_dir,
        tool_signatures=_get_mcp_tool_signatures(),
        contract_version=MCP_TOOL_CONTRACT_VERSION,
        concurrency=concurrency,
        test_command=test_command,
        lint_command=lint_command,
        build_command=build_command,
        allowed_paths=allowed_paths,
        task_config=task_config,
        timeout_sec=timeout_sec,
    )
    pipeline_result = solve_result.get("pipeline_result", {})
    review = pipeline_result.get("review", {})
    verification = pipeline_result.get("verification", {})
    application = pipeline_result.get("application", {})
    applied_paths = list(application.get("applied_output_paths", []))

    review_reason = str(review.get("reason", ""))
    verification_result = verification.get("result")
    verification_summary = (
        str(verification_result.get("summary", ""))
        if isinstance(verification_result, dict)
        else str(verification.get("summary", ""))
    )

    raw_provenance = solve_result.get("host_provenance", {})
    bounded_provenance = {
        "repository": str(raw_provenance.get("repository", "")),
        "model_class": str(raw_provenance.get("model_class", "")),
        "model_digest": str(raw_provenance.get("model_digest", "")),
        "execution_profile_id": str(
            raw_provenance.get("execution_profile_id", "")
        ),
        "model_source": str(raw_provenance.get("model_source", "")),
        "ollama_model": raw_provenance.get("ollama_model"),
        "contract_version": int(
            raw_provenance.get(
                "contract_version", MCP_TOOL_CONTRACT_VERSION
            )
        ),
    }

    return {
        "schema_version": 1,
        "interface": "swarm_execute",
        "host_provenance": bounded_provenance,
        "turn": int(pipeline_result.get("turn", 1)),
        "review": {
            "verdict": str(review.get("verdict", "UNKNOWN")),
            "reason": review_reason,
        },
        "verification": {
            "available": bool(verification.get("available", False)),
            "occurred": bool(verification.get("occurred", False)),
            "passed": bool(verification.get("passed", False)),
            "summary": verification_summary,
        },
        "application": {
            "available": bool(application.get("available", False)),
            "occurred": bool(application.get("occurred", False)),
            "applied_output_paths": applied_paths,
        },
        "output_files": applied_paths,
        "elapsed_sec": float(pipeline_result.get("elapsed_sec", 0.0)),
    }


@mcp.tool(name="swarm_execute")
def swarm_execute_tool(
    workspace: str,
    verification_workspace: str,
    task: dict[str, Any],
    state_dir: str | None = None,
    concurrency: int = 1,
    test_command: str | None = None,
    lint_command: str | None = None,
    build_command: str | None = None,
    allowed_paths: list[str] | None = None,
    task_config: dict[str, Any] | None = None,
    timeout_sec: int = 120,
) -> dict[str, Any]:
    """Execute swarm with canonical provenance and isolated verification."""
    return run_swarm_execute(
        workspace=workspace,
        verification_workspace=verification_workspace,
        task=task,
        state_dir=state_dir,
        concurrency=concurrency,
        test_command=test_command,
        lint_command=lint_command,
        build_command=build_command,
        allowed_paths=allowed_paths,
        task_config=task_config,
        timeout_sec=timeout_sec,
    )


def run_policy_status(
    workspace: str,
    *,
    mode: str = "coding",
    task_category: str = "unknown",
    state_dir: str | None = None,
) -> dict[str, Any]:
    """Inspect current v2 Effective Policy and promotion status using pinned adapter context."""
    ctx = HostAdapter.resolve_adapter_context(
        workspace,
        state_dir,
        tool_signatures=_get_mcp_tool_signatures(),
        contract_version=MCP_TOOL_CONTRACT_VERSION,
    )
    scope = Scope(
        mode=Mode(mode),
        repository=ctx.repository,
        task_category=TaskCategory(task_category),
        model_class=ctx.model_class,
    )
    return PolicyEngine(ctx.state_dir).get_status(scope, ctx.model_identity, ctx.execution_profile)


@mcp.tool(name="policy_status")
def policy_status_tool(
    workspace: str,
    mode: str = "coding",
    task_category: str = "unknown",
    state_dir: str | None = None,
) -> dict[str, Any]:
    """Inspect current Effective Policy, eligible successors, and signal receipts."""
    return run_policy_status(
        workspace=workspace,
        mode=mode,
        task_category=task_category,
        state_dir=state_dir,
    )


def run_policy_preview(
    workspace: str,
    *,
    candidate_id: str,
    evidence_bundle_id: str = "",
    mode: str = "coding",
    task_category: str = "unknown",
    state_dir: str | None = None,
) -> dict[str, Any]:
    """Evaluate and persist a bounded policy Preview without modifying active selection."""
    ctx = HostAdapter.resolve_adapter_context(
        workspace,
        state_dir,
        tool_signatures=_get_mcp_tool_signatures(),
        contract_version=MCP_TOOL_CONTRACT_VERSION,
    )
    scope = Scope(
        mode=Mode(mode),
        repository=ctx.repository,
        task_category=TaskCategory(task_category),
        model_class=ctx.model_class,
    )
    preview_id = f"preview-{secrets.randbelow(10**30):030d}"
    resolved_evidence_bundle_id = evidence_bundle_id or f"evidence-{secrets.randbelow(10**30):030d}"
    preview = Preview(
        preview_id=preview_id,
        scope=scope,
        candidate_id=candidate_id,
        evidence_bundle_id=resolved_evidence_bundle_id,
        model_digest=str(ctx.model_identity.artifact_digest),
        execution_profile_id=str(ctx.execution_profile.profile_id),
    )
    selection = PolicyEngine(ctx.state_dir).preview(preview, ctx.model_identity, ctx.execution_profile)
    return {
        "schema_version": ImmutableStateStore.schema_version,
        "interface": "policy_preview",
        "preview_id": preview_id,
        "evidence_bundle_id": resolved_evidence_bundle_id,
        "selection": {
            "policy_id": selection.policy.policy_id,
            "policy_version": selection.policy.version,
            "source": selection.source,
            "reason": selection.reason,
            "record_hash": selection.record_hash,
        },
    }


@mcp.tool(name="policy_preview")
def policy_preview_tool(
    workspace: str,
    candidate_id: str,
    evidence_bundle_id: str = "",
    mode: str = "coding",
    task_category: str = "unknown",
    state_dir: str | None = None,
) -> dict[str, Any]:
    """Evaluate a candidate policy without changing the active Champion."""
    return run_policy_preview(
        workspace=workspace,
        candidate_id=candidate_id,
        evidence_bundle_id=evidence_bundle_id,
        mode=mode,
        task_category=task_category,
        state_dir=state_dir,
    )


def run_policy_pin(
    workspace: str,
    *,
    candidate_id: str,
    mode: str = "coding",
    task_category: str = "unknown",
    state_dir: str | None = None,
) -> dict[str, Any]:
    """Persist a bounded Pin control locking policy selection to a designated candidate."""
    ctx = HostAdapter.resolve_adapter_context(
        workspace,
        state_dir,
        tool_signatures=_get_mcp_tool_signatures(),
        contract_version=MCP_TOOL_CONTRACT_VERSION,
    )
    scope = Scope(
        mode=Mode(mode),
        repository=ctx.repository,
        task_category=TaskCategory(task_category),
        model_class=ctx.model_class,
    )
    pin_id = f"pin-{secrets.randbelow(10**30):030d}"
    pin = Pin(
        pin_id=pin_id,
        scope=scope,
        candidate_id=candidate_id,
        model_digest=str(ctx.model_identity.artifact_digest),
        execution_profile_id=str(ctx.execution_profile.profile_id),
    )
    record = PolicyEngine(ctx.state_dir).pin(pin, ctx.model_identity, ctx.execution_profile)
    return {
        "schema_version": ImmutableStateStore.schema_version,
        "interface": "policy_pin",
        "pin_id": pin_id,
        "candidate_id": candidate_id,
        "record_hash": record.record_hash,
    }


@mcp.tool(name="policy_pin")
def policy_pin_tool(
    workspace: str,
    candidate_id: str,
    mode: str = "coding",
    task_category: str = "unknown",
    state_dir: str | None = None,
) -> dict[str, Any]:
    """Lock policy selection for the workspace to a specific candidate policy."""
    return run_policy_pin(
        workspace=workspace,
        candidate_id=candidate_id,
        mode=mode,
        task_category=task_category,
        state_dir=state_dir,
    )


def run_policy_rollback(
    workspace: str,
    *,
    reason: str,
    mode: str = "coding",
    task_category: str = "unknown",
    security_breach: bool = False,
    state_dir: str | None = None,
) -> dict[str, Any]:
    """Recover the active Champion and record a promotion notice."""
    ctx = HostAdapter.resolve_adapter_context(
        workspace,
        state_dir,
        tool_signatures=_get_mcp_tool_signatures(),
        contract_version=MCP_TOOL_CONTRACT_VERSION,
    )
    scope = Scope(
        mode=Mode(mode),
        repository=ctx.repository,
        task_category=TaskCategory(task_category),
        model_class=ctx.model_class,
    )
    notice = PolicyEngine(ctx.state_dir).rollback(
        scope=scope,
        model_identity=ctx.model_identity,
        execution_profile=ctx.execution_profile,
        reason=reason,
        security_breach=security_breach,
    )
    return {
        "schema_version": ImmutableStateStore.schema_version,
        "interface": "policy_rollback",
        "action": notice.action,
        "candidate_id": notice.candidate_id,
        "reason": notice.reason,
        "security_breach": security_breach,
        "inspect_command": notice.inspect_command,
        "rollback_command": notice.rollback_command,
    }


@mcp.tool(name="policy_rollback")
def policy_rollback_tool(
    workspace: str,
    reason: str,
    mode: str = "coding",
    task_category: str = "unknown",
    security_breach: bool = False,
    state_dir: str | None = None,
) -> dict[str, Any]:
    """Roll back the active Champion policy for this workspace."""
    return run_policy_rollback(
        workspace=workspace,
        reason=reason,
        mode=mode,
        task_category=task_category,
        security_breach=security_breach,
        state_dir=state_dir,
    )


def run_compute_scaling_status(
    workspace: str,
    *,
    mode: str = "coding",
    task_category: str = "unknown",
    state_dir: str | None = None,
) -> dict[str, Any]:
    """Inspect active compute scaling parameters for the workspace."""
    ctx = HostAdapter.resolve_adapter_context(
        workspace,
        state_dir,
        tool_signatures=_get_mcp_tool_signatures(),
        contract_version=MCP_TOOL_CONTRACT_VERSION,
    )
    scope = Scope(
        mode=Mode(mode),
        repository=ctx.repository,
        task_category=TaskCategory(task_category),
        model_class=ctx.model_class,
    )
    status = PolicyEngine(ctx.state_dir).get_scaling_status(
        scope=scope,
        model_identity=ctx.model_identity,
        execution_profile=ctx.execution_profile,
    )
    return {
        "schema_version": ImmutableStateStore.schema_version,
        "interface": "compute_scaling_status",
        "scope": status["scope"],
        "is_pinned": status["is_pinned"],
        "pin_id": status["pin_id"],
        "scaling_policy": status["scaling_policy"],
    }


@mcp.tool(name="compute_scaling_status")
def compute_scaling_status_tool(
    workspace: str,
    mode: str = "coding",
    task_category: str = "unknown",
    state_dir: str | None = None,
) -> dict[str, Any]:
    """Inspect the active compute scaling policy configuration
    for this workspace.
    """
    return run_compute_scaling_status(
        workspace=workspace,
        mode=mode,
        task_category=task_category,
        state_dir=state_dir,
    )


def run_compute_scaling_preview(
    workspace: str,
    *,
    variations: int = 3,
    temperature_schedule: list[float] | None = None,
    consensus_strategy: str = "min_diff",
    feedback_loop_enabled: bool = True,
    mode: str = "coding",
    task_category: str = "unknown",
    state_dir: str | None = None,
) -> dict[str, Any]:
    """Preview compute scaling parameters without persisting changes."""
    ctx = HostAdapter.resolve_adapter_context(
        workspace,
        state_dir,
        tool_signatures=_get_mcp_tool_signatures(),
        contract_version=MCP_TOOL_CONTRACT_VERSION,
    )
    scope = Scope(
        mode=Mode(mode),
        repository=ctx.repository,
        task_category=TaskCategory(task_category),
        model_class=ctx.model_class,
    )
    temp_sched = (
        tuple(temperature_schedule)
        if temperature_schedule is not None
        else (0.0, 0.35, 0.70)
    )
    preview = PolicyEngine(ctx.state_dir).preview_scaling(
        scope=scope,
        model_identity=ctx.model_identity,
        execution_profile=ctx.execution_profile,
        variations=variations,
        temperature_schedule=temp_sched,
        consensus_strategy=consensus_strategy,
        feedback_loop_enabled=feedback_loop_enabled,
    )
    return {
        "schema_version": ImmutableStateStore.schema_version,
        "interface": "compute_scaling_preview",
        "scope": preview["scope"],
        "preview_scaling_policy": preview["preview_scaling_policy"],
    }


@mcp.tool(name="compute_scaling_preview")
def compute_scaling_preview_tool(
    workspace: str,
    variations: int = 3,
    temperature_schedule: list[float] | None = None,
    consensus_strategy: str = "min_diff",
    feedback_loop_enabled: bool = True,
    mode: str = "coding",
    task_category: str = "unknown",
    state_dir: str | None = None,
) -> dict[str, Any]:
    """Preview custom compute scaling parameters without applying them."""
    return run_compute_scaling_preview(
        workspace=workspace,
        variations=variations,
        temperature_schedule=temperature_schedule,
        consensus_strategy=consensus_strategy,
        feedback_loop_enabled=feedback_loop_enabled,
        mode=mode,
        task_category=task_category,
        state_dir=state_dir,
    )


def run_compute_scaling_pin(
    workspace: str,
    *,
    variations: int = 3,
    temperature_schedule: list[float] | None = None,
    consensus_strategy: str = "min_diff",
    feedback_loop_enabled: bool = True,
    mode: str = "coding",
    task_category: str = "unknown",
    state_dir: str | None = None,
) -> dict[str, Any]:
    """Lock compute scaling parameters to a designated configuration."""
    ctx = HostAdapter.resolve_adapter_context(
        workspace,
        state_dir,
        tool_signatures=_get_mcp_tool_signatures(),
        contract_version=MCP_TOOL_CONTRACT_VERSION,
    )
    scope = Scope(
        mode=Mode(mode),
        repository=ctx.repository,
        task_category=TaskCategory(task_category),
        model_class=ctx.model_class,
    )
    temp_sched = (
        tuple(temperature_schedule)
        if temperature_schedule is not None
        else (0.0, 0.35, 0.70)
    )
    scaling_policy = ComputeScalingPolicy(
        variations=variations,
        temperature_schedule=temp_sched,
        consensus_strategy=consensus_strategy,
        feedback_loop_enabled=feedback_loop_enabled,
    )
    pin_id = f"cspin-{secrets.randbelow(10**30):030d}"
    pin = ComputeScalingPin(
        pin_id=pin_id,
        scope=scope,
        scaling_policy=scaling_policy,
        model_digest=str(ctx.model_identity.artifact_digest),
        execution_profile_id=str(ctx.execution_profile.profile_id),
    )
    record = PolicyEngine(ctx.state_dir).pin_scaling(
        pin, ctx.model_identity, ctx.execution_profile
    )
    return {
        "schema_version": ImmutableStateStore.schema_version,
        "interface": "compute_scaling_pin",
        "pin_id": pin_id,
        "record_hash": record.record_hash,
        "scaling_policy": {
            "variations": scaling_policy.variations,
            "temperature_schedule": list(scaling_policy.temperature_schedule),
            "consensus_strategy": scaling_policy.consensus_strategy,
            "feedback_loop_enabled": scaling_policy.feedback_loop_enabled,
        },
    }


@mcp.tool(name="compute_scaling_pin")
def compute_scaling_pin_tool(
    workspace: str,
    variations: int = 3,
    temperature_schedule: list[float] | None = None,
    consensus_strategy: str = "min_diff",
    feedback_loop_enabled: bool = True,
    mode: str = "coding",
    task_category: str = "unknown",
    state_dir: str | None = None,
) -> dict[str, Any]:
    """Pin and lock compute scaling parameters for the workspace."""
    return run_compute_scaling_pin(
        workspace=workspace,
        variations=variations,
        temperature_schedule=temperature_schedule,
        consensus_strategy=consensus_strategy,
        feedback_loop_enabled=feedback_loop_enabled,
        mode=mode,
        task_category=task_category,
        state_dir=state_dir,
    )


@mcp.tool(name="verify")
def verify_tool(
    workspace: str,
    test_command: str | None = None,
    lint_command: str | None = None,
    build_command: str | None = None,
    allowed_paths: list[str] | None = None,
    timeout_sec: int = 120,
) -> dict:
    """Run project verification checks (tests, lint, build, and scope)."""
    return run_verify(
        workspace,
        test_command,
        lint_command,
        build_command,
        allowed_paths,
        timeout_sec,
    )


@mcp.tool(name="setup_workspace")
def setup_workspace_tool(
    workspace: str,
    repository: str,
    ollama_model: str | None = None,
    model_digest: str | None = None,
    model_class: str = "unknown",
    effective_context_limit: int = 8192,
    runtime_kind: str = "",
    runtime_version: str = "",
    replace: bool = False,
) -> dict[str, str | bool]:
    """Pin an exact Ollama or host-supplied model identity for automatic Signal collection."""
    return run_setup_workspace(
        workspace, repository, ollama_model=ollama_model, model_digest=model_digest,
        model_class=model_class, effective_context_limit=effective_context_limit,
        runtime_kind=runtime_kind, runtime_version=runtime_version, replace=replace,
    )


@mcp.tool(name="recording_audit")
def recording_audit_tool(workspace: str, receipt_hash: str, after: str) -> dict[str, bool | int]:
    """Check whether the exact receipt returned by a host task was recorded after its start time."""
    return run_recording_audit(workspace, receipt_hash, after)


@mcp.tool(name="verify_and_record")
def verify_and_record_tool(
    workspace: str,
    state_dir: str | None = None,
    task_category: str = "unknown",
    retry_count: int = 0,
    test_command: str | None = None,
    lint_command: str | None = None,
    build_command: str | None = None,
    allowed_paths: list[str] | None = None,
    timeout_sec: int = 120,
) -> dict:
    """Run verification and record a privacy-safe v2 Signal using the pinned adapter identity."""
    return run_verify_and_record(
        workspace,
        state_dir=state_dir,
        task_category=task_category,
        retry_count=retry_count,
        test_command=test_command,
        lint_command=lint_command,
        build_command=build_command,
        allowed_paths=allowed_paths,
        timeout_sec=timeout_sec,
    )


@mcp.tool(name="protocol")
def protocol_tool(task_description: str, complexity: str = "medium") -> dict[str, str]:
    """Get the Mighty Mouse structured coding protocol for the current task."""
    return run_protocol(task_description, complexity)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
