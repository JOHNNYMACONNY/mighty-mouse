"""Conservative project-check auto-detection."""

from __future__ import annotations

import json
import os
import shutil
import sys


def _has_python_tests(workspace: str) -> bool:
    for root, dirs, files in os.walk(workspace):
        dirs[:] = [d for d in dirs if d not in {".git", ".venv", "node_modules"}]
        if any(name.startswith("test_") and name.endswith(".py") for name in files):
            return True
        if "tests" in dirs:
            return True
    return False


def _node_scripts(workspace: str) -> dict[str, str]:
    package_path = os.path.join(workspace, "package.json")
    try:
        with open(package_path, encoding="utf-8") as package_file:
            package = json.load(package_file)
    except (OSError, json.JSONDecodeError):
        return {}
    scripts = package.get("scripts", {})
    return scripts if isinstance(scripts, dict) else {}


def detect_checks(workspace: str) -> tuple[list[tuple[str, list[str]]], list[str]]:
    """Return safe argument-vector checks and detection warnings."""
    checks: list[tuple[str, list[str]]] = []
    warnings: list[str] = []

    has_python = any(
        os.path.exists(os.path.join(workspace, marker))
        for marker in ("pyproject.toml", "setup.py", "setup.cfg")
    )
    if has_python:
        if _has_python_tests(workspace):
            checks.append(("python-tests", [sys.executable, "-m", "pytest", "-q"]))
        else:
            checks.append(("python-syntax", [sys.executable, "-m", "compileall", "-q", "."]))
            warnings.append("No Python tests detected; running syntax validation only.")

    package_path = os.path.join(workspace, "package.json")
    if os.path.exists(package_path):
        scripts = _node_scripts(workspace)
        test_script = str(scripts.get("test", ""))
        if test_script and "no test specified" not in test_script.lower():
            checks.append(("node-tests", ["npm", "test"]))
        elif "lint" in scripts:
            checks.append(("node-lint", ["npm", "run", "lint"]))
            warnings.append("No Node.js test script detected; running lint only.")
        elif "build" in scripts:
            checks.append(("node-build", ["npm", "run", "build"]))
            warnings.append("No Node.js test or lint script detected; running build only.")
        else:
            warnings.append("Node.js project detected without test, lint, or build scripts.")

    if os.path.exists(os.path.join(workspace, "Cargo.toml")):
        checks.append(("rust-tests", ["cargo", "test"]))
    if os.path.exists(os.path.join(workspace, "go.mod")):
        checks.append(("go-tests", ["go", "test", "./..."]))

    available_checks = []
    for name, command in checks:
        executable = command[0]
        if os.path.isabs(executable):
            available = os.path.exists(executable)
        else:
            available = shutil.which(executable) is not None
        if not available:
            warnings.append(f"Skipped {name}: executable not found: {executable}")
        else:
            available_checks.append((name, command))

    return available_checks, warnings
