from __future__ import annotations

import json
import sys

from mighty_mouse.verifier import VerificationResult, verify


def _indent(text: str) -> str:
    return "\n".join(f"    {line}" for line in text.rstrip().splitlines())


def render_result(result: VerificationResult) -> str:
    lines: list[str] = []
    for check in result.checks:
        status = "PASS" if check.passed else "FAIL"
        lines.append(f"{status} {check.name} ({check.duration_sec:.2f}s)")
        if check.output.strip():
            lines.append(_indent(check.output))

    lines.append(result.summary)
    warnings = getattr(result, "warnings", [])
    if warnings:
        lines.append("Detection warnings:")
        lines.extend(f"  - {warning}" for warning in warnings)
    if result.suggestions:
        lines.append("Suggestions:")
        lines.extend(f"  - {suggestion}" for suggestion in result.suggestions)
    return "\n".join(lines)


def result_document(result: VerificationResult) -> dict:
    return {
        "schema_version": 1,
        "interface": "verify",
        **result.to_dict(),
    }


def run_verify(
    workspace: str,
    test_command: str | None = None,
    lint_command: str | None = None,
    build_command: str | None = None,
    allowed_paths: list[str] | None = None,
    timeout_sec: int = 120,
    json_output: bool = False,
) -> None:
    try:
        result = verify(
            workspace=workspace,
            test_command=test_command,
            lint_command=lint_command,
            build_command=build_command,
            allowed_paths=allowed_paths,
            timeout_sec=timeout_sec,
        )
    except (OSError, ValueError) as exc:
        if json_output:
            print(json.dumps({
                "schema_version": 1,
                "interface": "verify",
                "passed": False,
                "checks": [],
                "summary": str(exc),
                "suggestions": ["Provide a readable project workspace and run verification again."],
            }))
            raise SystemExit(2) from exc
        print(f"mighty-mouse verify: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc

    print(json.dumps(result_document(result)) if json_output else render_result(result))
    raise SystemExit(0 if result.passed else 1)
