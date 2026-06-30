"""Human-readable command-line interface for project verification."""

from __future__ import annotations

import sys

from mighty_mouse.verifier import verify


def run_verify(
    workspace: str,
    test_command: str | None = None,
    lint_command: str | None = None,
    build_command: str | None = None,
    allowed_paths: list[str] | None = None,
    timeout_sec: int = 120,
) -> None:
    """Run the generic verifier, print its result, and exit with a CLI status."""
    try:
        result = verify(
            workspace=workspace,
            test_command=test_command,
            lint_command=lint_command,
            build_command=build_command,
            allowed_paths=allowed_paths,
            timeout_sec=timeout_sec,
        )
    except (TypeError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc

    for check in result.checks:
        status = "PASS" if check.passed else "FAIL"
        print(f"[{status}] {check.name} ({check.duration_sec:.3f}s)")
        if check.output:
            for line in check.output.splitlines():
                print(f"  {line}")

    print(result.summary)
    for suggestion in result.suggestions:
        print(f"Suggestion: {suggestion}")

    raise SystemExit(0 if result.passed else 1)
