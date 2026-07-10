#!/usr/bin/env python3
"""Validate private held-out tasks before freezing a scored corpus."""

from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

from eval.run_local_model_pilot import _run_baseline_checks, load_task
from eval.run_local_model_study import _resolve_held_out_check_paths


def _copy_template(template: Path, destination: Path) -> None:
    shutil.copytree(
        template,
        destination,
        symlinks=True,
        ignore=shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache", "node_modules"),
    )


def validate_task(task_path: Path) -> dict[str, Any]:
    task, template = load_task(task_path)
    task_for_checks = _resolve_held_out_check_paths(task, template)
    solution_name = task.get("solution_template")
    if not isinstance(solution_name, str) or not solution_name:
        raise ValueError(f"Task must define solution_template: {task['id']}")
    solution = (task_path.resolve().parent / solution_name).resolve()
    if not solution.is_dir():
        raise ValueError(f"solution_template is not a directory: {task['id']}")
    with tempfile.TemporaryDirectory(prefix="mighty-mouse-task-validate-") as temp:
        root = Path(temp)
        baseline = root / "baseline"
        solved = root / "solved"
        _copy_template(template, baseline)
        _copy_template(template, solved)
        for source in solution.rglob("*"):
            if not source.is_file():
                continue
            relative = source.relative_to(solution)
            target = solved / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        baseline_checks = _run_baseline_checks(task_for_checks, baseline)
        solved_checks = _run_baseline_checks(task_for_checks, solved)
    acceptance = task_for_checks.get("acceptance_checks") or task_for_checks["checks"]
    if not acceptance:
        raise ValueError(f"Task has no acceptance checks: {task['id']}")
    if all(row["passed"] for row in baseline_checks.values()):
        raise ValueError(f"Task baseline is already solved: {task['id']}")
    if not all(row["passed"] for row in solved_checks.values()):
        raise ValueError(f"Known solution fails acceptance checks: {task['id']}")
    return {
        "task_id": task["id"],
        "baseline": {name: row["passed"] for name, row in baseline_checks.items()},
        "solution": {name: row["passed"] for name, row in solved_checks.items()},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a private held-out task fixture")
    parser.add_argument("task", type=Path)
    args = parser.parse_args()
    print(json.dumps(validate_task(args.task), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
