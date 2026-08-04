"""Mighty Mouse MCP stdio server."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
import secrets

from mcp.server.fastmcp import FastMCP

from mighty_mouse.host.adapter import (
    ADAPTER_CONFIG_FILENAME,
    MCP_ADAPTER_CONFIG_SCHEMA_VERSION,
    MCP_TOOL_CONTRACT_VERSION,
    SUPPORTED_RUNTIME_KINDS,
    HostAdapter,
)
from mighty_mouse.protocols import PROTOCOL_VERSION, get_protocol
from mighty_mouse.v2.foundation import Mode, Scope, Signal, TaskCategory
from mighty_mouse.v2.signals import SignalLifecycle
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
    signal = Signal(
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
    lifecycle = SignalLifecycle(resolved_state_dir)
    receipt_hash = lifecycle.collect(signal)
    return {
        "verification": verification,
        "signal_recorded": receipt_hash is not None,
        "receipt_hash": receipt_hash,
    }


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
