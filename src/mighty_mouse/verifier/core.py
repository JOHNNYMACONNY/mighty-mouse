"""Generic verification for real software projects."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import os
import shlex
import subprocess
import time
from typing import Sequence

from .detect import detect_checks, detect_projects
from .scope import check_scope

MAX_OUTPUT_CHARS = 12_000


@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool
    output: str
    duration_sec: float

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class VerificationResult:
    passed: bool
    checks: list[CheckResult]
    summary: str
    suggestions: list[str] = field(default_factory=list)
    detected_projects: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "checks": [check.to_dict() for check in self.checks],
            "summary": self.summary,
            "suggestions": list(self.suggestions),
            "detected_projects": list(self.detected_projects),
            "warnings": list(self.warnings),
        }


def _command_args(command: str | Sequence[str]) -> list[str]:
    args = shlex.split(command) if isinstance(command, str) else list(command)
    if not args or not all(isinstance(part, str) and part for part in args):
        raise ValueError("Verification commands must contain at least one non-empty argument.")
    return args


def _truncate(output: str) -> str:
    if len(output) <= MAX_OUTPUT_CHARS:
        return output
    omitted = len(output) - MAX_OUTPUT_CHARS
    return output[:MAX_OUTPUT_CHARS] + f"\n...[truncated {omitted} characters]"


def _run_check(name: str, command: str | Sequence[str], workspace: str, timeout_sec: int) -> CheckResult:
    args = _command_args(command)
    started = time.monotonic()
    try:
        result = subprocess.run(
            args,
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            env={**os.environ, "CI": "1"},
        )
        output = (result.stdout + result.stderr).strip()
        passed = result.returncode == 0
    except subprocess.TimeoutExpired as exc:
        output = f"Timed out after {timeout_sec}s.\n{exc.stdout or ''}{exc.stderr or ''}"
        passed = False
    except OSError as exc:
        output = f"Unable to execute {args[0]}: {exc}"
        passed = False
    duration = round(time.monotonic() - started, 3)
    return CheckResult(name=name, passed=passed, output=_truncate(output), duration_sec=duration)


def verify(
    workspace: str,
    test_command: str | Sequence[str] | None = None,
    lint_command: str | Sequence[str] | None = None,
    build_command: str | Sequence[str] | None = None,
    allowed_paths: list[str] | None = None,
    timeout_sec: int = 120,
) -> VerificationResult:
    """Run applicable checks and return a structured, provider-neutral result."""
    workspace = os.path.abspath(workspace)
    if not os.path.isdir(workspace):
        raise ValueError(f"Workspace is not a directory: {workspace}")
    if timeout_sec < 1:
        raise ValueError("timeout_sec must be at least 1")

    commands: list[tuple[str, str | Sequence[str]]] = []
    warnings: list[str] = []
    detected_projects: list[str] = []
    if test_command is not None:
        commands.append(("tests", test_command))
    if lint_command is not None:
        commands.append(("lint", lint_command))
    if build_command is not None:
        commands.append(("build", build_command))
    if not commands:
        detected_projects = detect_projects(workspace)
        detected, warnings = detect_checks(workspace)
        commands.extend(detected)

    checks = [
        _run_check(name, command, workspace, timeout_sec)
        for name, command in commands
    ]

    if allowed_paths is not None:
        started = time.monotonic()
        scope_passed, scope_output, violations = check_scope(workspace, allowed_paths)
        checks.append(
            CheckResult(
                name="scope",
                passed=scope_passed,
                output=scope_output,
                duration_sec=round(time.monotonic() - started, 3),
            )
        )
        if violations:
            warnings.append("Revert or explicitly allow the out-of-scope paths.")

    if not checks:
        return VerificationResult(
            passed=False,
            checks=[],
            summary="No executable verification checks were detected.",
            suggestions=warnings + ["Add tests or pass an explicit test, lint, or build command."],
            detected_projects=detected_projects,
            warnings=warnings,
        )

    failed = [check.name for check in checks if not check.passed]
    suggestions = list(warnings)
    suggestions.extend(f"Fix the failing {name} check and run verification again." for name in failed)
    passed = not failed
    summary = (
        f"Passed {len(checks)}/{len(checks)} verification checks."
        if passed
        else f"Failed {len(failed)}/{len(checks)} verification checks: {', '.join(failed)}."
    )
    return VerificationResult(
        passed=passed,
        checks=checks,
        summary=summary,
        suggestions=suggestions,
        detected_projects=detected_projects,
        warnings=warnings,
    )
