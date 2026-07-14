"""Mighty Mouse MCP stdio server."""

from __future__ import annotations

import json
from pathlib import Path
import secrets

from mcp.server.fastmcp import FastMCP

from mighty_mouse.protocols import PROTOCOL_VERSION, get_protocol
from mighty_mouse.verifier import verify as verify_workspace
from mighty_mouse.v2.foundation import Mode, Scope, Signal, TaskCategory
from mighty_mouse.v2.signals import SignalLifecycle

mcp = FastMCP("mighty-mouse")
ADAPTER_CONFIG_FILENAME = "cline-adapter.json"


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
    return resolved_state_dir, scope, config["model_digest"], config["execution_profile_id"]


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
