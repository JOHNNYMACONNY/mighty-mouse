"""Mighty Mouse MCP stdio server."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from hashlib import sha256
import inspect
from pathlib import Path
import secrets

from mcp.server.fastmcp import FastMCP

from mighty_mouse.protocols import PROTOCOL_VERSION, get_protocol
from mighty_mouse.verifier import verify as verify_workspace
from mighty_mouse.v2.foundation import Mode, Scope, Signal, TaskCategory, resolve_execution_profile
from mighty_mouse.v2.signals import SignalLifecycle

mcp = FastMCP("mighty-mouse")
ADAPTER_CONFIG_FILENAME = "mcp-adapter.json"
SUPPORTED_RUNTIME_KINDS = frozenset({"cline", "claude-code", "codex", "cursor", "antigravity", "hermes", "windsurf"})
MCP_TOOL_CONTRACT_VERSION = 1
MCP_ADAPTER_CONFIG_SCHEMA_VERSION = 2


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


def _adapter_scope(workspace: str, state_dir: str | None, task_category: str) -> tuple[Path, Scope, str, str]:
    resolved_state_dir = Path(state_dir) if state_dir else Path(workspace) / ".mighty-mouse"
    path = resolved_state_dir / ADAPTER_CONFIG_FILENAME
    if not path.is_file():
        raise ValueError(f"MCP adapter identity is not configured: {path}; run setup_workspace")
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("Cline adapter identity configuration is invalid JSON") from exc
    base_scope = _adapter_scope_from_config(config)
    scope = Scope(Mode.CODING, base_scope.repository, TaskCategory(task_category), base_scope.model_class)
    return resolved_state_dir, scope, config["model_digest"], config["execution_profile_id"]


def _ollama_model_digest(model: str) -> str:
    name, separator, tag = model.rpartition(":")
    if not separator:
        name, tag = model, "latest"
    if not name or not tag or any(part in {"", ".", ".."} for part in name.split("/")):
        raise ValueError("Ollama model must be a model name with an optional tag")
    manifest_path = Path.home() / ".ollama" / "models" / "manifests" / "registry.ollama.ai" / "library" / name / tag
    if not manifest_path.is_file():
        raise ValueError(f"Ollama manifest is unavailable for {model}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Ollama manifest is invalid for {model}") from exc
    digest = next((layer.get("digest") for layer in manifest.get("layers", []) if layer.get("mediaType") == "application/vnd.ollama.image.model"), None)
    if not isinstance(digest, str):
        raise ValueError(f"Ollama model-layer digest is unavailable for {model}")
    return digest


def _mcp_tool_contract() -> dict[str, str]:
    return {
        "contract_version": str(MCP_TOOL_CONTRACT_VERSION),
        "protocol": str(inspect.signature(run_protocol)),
        "verify": str(inspect.signature(run_verify)),
        "setup_workspace": str(inspect.signature(run_setup_workspace)),
        "verify_and_record": str(inspect.signature(run_verify_and_record)),
        "recording_audit": str(inspect.signature(run_recording_audit)),
    }


def _current_execution_profile(*, runtime_kind: str, runtime_version: str, effective_context_limit: int):
    if runtime_kind not in SUPPORTED_RUNTIME_KINDS or not runtime_version or runtime_version == "unknown":
        raise ValueError("Workspace setup requires a supported runtime kind and exact runtime version")
    tool_contract = _mcp_tool_contract()
    tool_contract_digest = "sha256:" + sha256(
        json.dumps(tool_contract, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    prompt_template_digest = "sha256:" + sha256(
        "\n".join(get_protocol(complexity) for complexity in ("low", "medium", "high")).encode()
    ).hexdigest()
    profile = resolve_execution_profile(
        runtime_kind=runtime_kind, runtime_version=runtime_version,
        effective_context_limit=effective_context_limit,
        tool_contract_digest=tool_contract_digest, prompt_template_digest=prompt_template_digest,
        sampling_settings={}, resource_limits={}, capabilities=frozenset({"mcp", *tool_contract}),
    )
    return profile, tool_contract_digest, prompt_template_digest


def _adapter_config(
    *, repository: str, model_digest: str, model_class: str, effective_context_limit: int,
    runtime_kind: str, runtime_version: str, ollama_model: str | None,
) -> dict[str, str | int]:
    profile, tool_contract_digest, prompt_template_digest = _current_execution_profile(
        runtime_kind=runtime_kind, runtime_version=runtime_version,
        effective_context_limit=effective_context_limit,
    )
    config = {
        "schema_version": MCP_ADAPTER_CONFIG_SCHEMA_VERSION,
        "repository": repository, "model_digest": model_digest, "model_class": model_class,
        "model_source": "ollama" if ollama_model else "host", "ollama_model": ollama_model,
        "execution_profile_id": profile.profile_id, "runtime_kind": runtime_kind,
        "runtime_version": runtime_version, "effective_context_limit": effective_context_limit,
        "tool_contract_digest": tool_contract_digest, "prompt_template_digest": prompt_template_digest,
    }
    _adapter_scope_from_config(config)
    return config


def _adapter_scope_from_config(config: dict[str, str | int]) -> Scope:
    required = {
        "schema_version", "repository", "model_digest", "model_class", "execution_profile_id",
        "model_source", "ollama_model", "runtime_kind", "runtime_version", "effective_context_limit", "tool_contract_digest",
        "prompt_template_digest",
    }
    if set(config) != required:
        raise ValueError("MCP adapter identity configuration is stale or invalid; run setup_workspace")
    if config["schema_version"] != MCP_ADAPTER_CONFIG_SCHEMA_VERSION:
        raise ValueError("MCP adapter identity configuration is stale; run setup_workspace")
    if config["model_source"] not in {"ollama", "host"}:
        raise ValueError("MCP adapter identity configuration is stale or invalid; run setup_workspace")
    if config["model_source"] == "ollama":
        ollama_model = config["ollama_model"]
        if not isinstance(ollama_model, str) or _ollama_model_digest(ollama_model) != config["model_digest"]:
            raise ValueError("MCP adapter model identity changed; run setup_workspace")
    elif config["ollama_model"] is not None:
        raise ValueError("MCP adapter identity configuration is stale or invalid; run setup_workspace")
    profile, tool_contract_digest, prompt_template_digest = _current_execution_profile(
        runtime_kind=str(config["runtime_kind"]), runtime_version=str(config["runtime_version"]),
        effective_context_limit=int(config["effective_context_limit"]),
    )
    if (
        config["execution_profile_id"] != profile.profile_id
        or config["tool_contract_digest"] != tool_contract_digest
        or config["prompt_template_digest"] != prompt_template_digest
    ):
        raise ValueError("MCP adapter identity configuration is stale; run setup_workspace")
    scope = Scope(Mode.CODING, config["repository"], TaskCategory.UNKNOWN, config["model_class"])
    Signal(
        signal_id="signal-000", scope=scope, model_digest=config["model_digest"],
        execution_profile_id=str(config["execution_profile_id"]), outcome="passed", duration_ms=0,
        retry_count=0, verifier_category="none", verifier_result="not_run",
    )
    return scope


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
