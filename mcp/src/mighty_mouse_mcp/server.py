"""Mighty Mouse MCP stdio server."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import secrets

from mcp.server.fastmcp import FastMCP

from mighty_mouse.protocols import PROTOCOL_VERSION, get_protocol
from mighty_mouse.verifier import verify as verify_workspace
from mighty_mouse.v2.foundation import Mode, Scope, Signal, TaskCategory, resolve_execution_profile
from mighty_mouse.v2.signals import SignalLifecycle

mcp = FastMCP("mighty-mouse")
ADAPTER_CONFIG_FILENAME = "mcp-adapter.json"
LEGACY_ADAPTER_CONFIG_FILENAME = "cline-adapter.json"


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
        legacy_path = resolved_state_dir / LEGACY_ADAPTER_CONFIG_FILENAME
        path = legacy_path if legacy_path.is_file() else path
    if not path.is_file():
        raise ValueError(f"Cline adapter identity is not configured: {path}")
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("Cline adapter identity configuration is invalid JSON") from exc
    required = {"repository", "model_digest", "model_class", "execution_profile_id"}
    if set(config) != required:
        raise ValueError("Cline adapter identity configuration has an invalid shape")
    scope = Scope(Mode.CODING, config["repository"], TaskCategory(task_category), config["model_class"])
    # Signal validates digest/profile formats. Refuse unknown provenance for automatic learning.
    if config["execution_profile_id"] == "unknown":
        raise ValueError("Cline adapter identity configuration requires an exact execution profile digest")
    Signal(
        signal_id="signal-000", scope=scope, model_digest=config["model_digest"],
        execution_profile_id=config["execution_profile_id"], outcome="passed", duration_ms=0,
        retry_count=0, verifier_category="none", verifier_result="not_run",
    )
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


def _adapter_config(
    *, repository: str, ollama_model: str, model_class: str, effective_context_limit: int,
    runtime_kind: str, runtime_version: str,
) -> dict[str, str]:
    model_digest = _ollama_model_digest(ollama_model)
    tool_contract_digest = "sha256:" + sha256(f"mighty-mouse-mcp:{PROTOCOL_VERSION}".encode()).hexdigest()
    prompt_template_digest = "sha256:" + sha256(
        "\n".join(get_protocol(complexity) for complexity in ("low", "medium", "high")).encode()
    ).hexdigest()
    profile = resolve_execution_profile(
        runtime_kind=runtime_kind, runtime_version=runtime_version,
        effective_context_limit=effective_context_limit,
        tool_contract_digest=tool_contract_digest, prompt_template_digest=prompt_template_digest,
        sampling_settings={}, resource_limits={}, capabilities={"mcp", "protocol", "verify"},
    )
    config = {
        "repository": repository, "model_digest": model_digest, "model_class": model_class,
        "execution_profile_id": profile.profile_id,
    }
    _adapter_scope_from_config(config)
    return config


def _adapter_scope_from_config(config: dict[str, str]) -> Scope:
    required = {"repository", "model_digest", "model_class", "execution_profile_id"}
    if set(config) != required:
        raise ValueError("Cline adapter identity configuration has an invalid shape")
    scope = Scope(Mode.CODING, config["repository"], TaskCategory.UNKNOWN, config["model_class"])
    Signal(
        signal_id="signal-000", scope=scope, model_digest=config["model_digest"],
        execution_profile_id=config["execution_profile_id"], outcome="passed", duration_ms=0,
        retry_count=0, verifier_category="none", verifier_result="not_run",
    )
    return scope


def run_setup_workspace(
    workspace: str, repository: str, ollama_model: str, model_class: str = "unknown",
    effective_context_limit: int = 8192, runtime_kind: str = "unknown", runtime_version: str = "unknown",
    replace: bool = False,
) -> dict[str, str | bool]:
    """Pin the local Ollama and Cline identity needed for automatic Signal collection."""
    workspace_path = Path(workspace)
    if not workspace_path.is_dir():
        raise ValueError(f"Workspace is not a directory: {workspace}")
    config = _adapter_config(
        repository=repository, ollama_model=ollama_model, model_class=model_class,
        effective_context_limit=effective_context_limit, runtime_kind=runtime_kind, runtime_version=runtime_version,
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


def run_recording_audit(workspace: str, after: str | None = None) -> dict[str, bool | int]:
    """Return whether a content-free Signal was recorded after a host task began."""
    threshold = datetime.fromisoformat(after) if after else None
    if threshold is not None:
        threshold = threshold.astimezone(timezone.utc) if threshold.tzinfo else threshold.replace(tzinfo=timezone.utc)
    lifecycle = SignalLifecycle(Path(workspace) / ".mighty-mouse")
    count = sum(
        1 for receipt in lifecycle._receipts()
        if threshold is None or datetime.fromisoformat(receipt["recorded_at"]).astimezone(timezone.utc) >= threshold
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
    ollama_model: str,
    model_class: str = "unknown",
    effective_context_limit: int = 8192,
    runtime_kind: str = "unknown",
    runtime_version: str = "unknown",
    replace: bool = False,
) -> dict[str, str | bool]:
    """Pin the local Ollama/Cline identity for automatic content-free Signal collection."""
    return run_setup_workspace(
        workspace, repository, ollama_model, model_class, effective_context_limit, runtime_kind, runtime_version, replace,
    )


@mcp.tool(name="recording_audit")
def recording_audit_tool(workspace: str, after: str | None = None) -> dict[str, bool | int]:
    """Check whether a host task recorded a Signal after its start time."""
    return run_recording_audit(workspace, after)


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
