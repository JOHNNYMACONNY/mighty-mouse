#!/usr/bin/env python3
"""Fail when changed Python lines introduce Flake8 violations."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from typing import Iterable


HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
VIOLATION_RE = re.compile(
    r"^(?P<path>.+?):(?P<line>\d+):(?P<column>\d+):"
    r"(?P<code>[A-Z]\d{3}) (?P<message>.+)$"
)


@dataclass(frozen=True)
class Violation:
    path: str
    line: int
    column: int
    code: str
    message: str

    def render(self) -> str:
        return (
            f"{self.path}:{self.line}:{self.column}: "
            f"{self.code} {self.message}"
        )


def parse_changed_lines(diff_text: str) -> dict[str, set[int]]:
    """Return added-line numbers grouped by new-file path."""

    changed: dict[str, set[int]] = {}
    current_path: str | None = None
    next_line: int | None = None

    for raw_line in diff_text.splitlines():
        if raw_line.startswith("+++ b/"):
            current_path = raw_line[6:]
            changed.setdefault(current_path, set())
            next_line = None
            continue
        if raw_line.startswith("+++ /dev/null"):
            current_path = None
            next_line = None
            continue

        hunk = HUNK_RE.match(raw_line)
        if hunk:
            next_line = int(hunk.group(1))
            continue
        if (
            current_path is None
            or next_line is None
            or raw_line.startswith("\\")
        ):
            continue

        if raw_line.startswith("+"):
            changed[current_path].add(next_line)
            next_line += 1
        elif raw_line.startswith("-"):
            continue
        else:
            next_line += 1

    return {path: lines for path, lines in changed.items() if lines}


def parse_violations(output: str) -> tuple[list[Violation], list[str]]:
    """Parse Flake8 output, retaining unexpected lines as hard errors."""

    violations: list[Violation] = []
    unparsed: list[str] = []
    for raw_line in output.splitlines():
        if not raw_line.strip():
            continue
        match = VIOLATION_RE.match(raw_line)
        if match is None:
            unparsed.append(raw_line)
            continue
        violations.append(
            Violation(
                path=match.group("path"),
                line=int(match.group("line")),
                column=int(match.group("column")),
                code=match.group("code"),
                message=match.group("message"),
            )
        )
    return violations, unparsed


def filter_changed_violations(
    violations: Iterable[Violation], changed_lines: dict[str, set[int]]
) -> list[Violation]:
    """Keep violations whose file and line came from the current diff."""

    return [
        violation
        for violation in violations
        if violation.line in changed_lines.get(violation.path, set())
    ]


def _git_diff(base: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "git",
            "-c",
            "core.fsmonitor=false",
            "-c",
            "core.untrackedCache=false",
            "diff",
            "--unified=0",
            "--diff-filter=ACMRTUXB",
            f"{base}...HEAD",
            "--",
            "*.py",
        ],
        check=False,
        capture_output=True,
        text=True,
    )


def _run_flake8(paths: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "flake8",
            "--format=%(path)s:%(row)d:%(col)d:%(code)s %(text)s",
            *paths,
        ],
        check=False,
        capture_output=True,
        text=True,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base",
        required=True,
        help="Base revision for three-dot Git diff",
    )
    args = parser.parse_args(argv)

    diff_result = _git_diff(args.base)
    if diff_result.returncode != 0:
        sys.stderr.write(diff_result.stderr)
        return 2

    changed_lines = parse_changed_lines(diff_result.stdout)
    paths = sorted(changed_lines)
    if not paths:
        print("No changed Python lines.")
        return 0

    flake8_result = _run_flake8(paths)
    if flake8_result.returncode not in (0, 1) or flake8_result.stderr:
        print(
            f"Flake8 failed with exit code {flake8_result.returncode}.",
            file=sys.stderr,
        )
        if flake8_result.stderr:
            print(flake8_result.stderr, file=sys.stderr, end="")
        return 2

    violations, unparsed = parse_violations(flake8_result.stdout)
    if unparsed:
        print("Unable to parse Flake8 output:", file=sys.stderr)
        print("\n".join(unparsed), file=sys.stderr)
        return 2

    new_violations = filter_changed_violations(violations, changed_lines)
    if new_violations:
        print("New Flake8 violations on changed lines:", file=sys.stderr)
        for violation in new_violations:
            print(violation.render(), file=sys.stderr)
        return 1

    ignored = len(violations) - len(new_violations)
    print(f"Changed-line Flake8 clean; ignored {ignored} baseline violations.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
