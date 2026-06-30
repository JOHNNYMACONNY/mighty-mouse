"""Mighty Mouse MCP stdio server."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from mighty_mouse.protocols import PROTOCOL_VERSION, get_protocol
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
            "After editing, call mighty-mouse/verify. Fix failures and retry up to three rounds."
        ),
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


@mcp.tool(name="protocol")
def protocol_tool(task_description: str, complexity: str = "medium") -> dict[str, str]:
    """Get the Mighty Mouse structured coding protocol for the current task."""
    return run_protocol(task_description, complexity)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
