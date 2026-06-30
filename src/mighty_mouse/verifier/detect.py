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


def _node_scripts(workspace: str) -> tuple[dict[str, str] | None, str | None]:
    package_path = os.path.join(workspace, "package.json")
    try:
        with open(package_path, encoding="utf-8") as package_file:
            package = json.load(package_file)
    except OSError as exc:
        return None, f"Unable to read package.json: {exc}"
    except json.JSONDecodeError as exc:
        return None, f"Invalid package.json: {exc.msg} (line {exc.lineno}, column {exc.colno})."
    if not isinstance(package, dict):
        return None, "Invalid package.json: the top-level value must be an object."
    scripts = package.get("scripts", {})
    if not isinstance(scripts, dict):
        return None, "Invalid package.json: 'scripts' must be an object."
    return scripts, None


def detect_projects(workspace: str) -> list[str]:
    """Return every project ecosystem identified by a root marker."""
    projects: list[str] = []
    if any(
        os.path.exists(os.path.join(workspace, marker))
        for marker in ("pyproject.toml", "setup.py", "setup.cfg")
    ):
        projects.append("python")
    if os.path.exists(os.path.join(workspace, "package.json")):
        projects.append("node")
    if os.path.exists(os.path.join(workspace, "Cargo.toml")):
        projects.append("rust")
    if os.path.exists(os.path.join(workspace, "go.mod")):
        projects.append("go")
    return projects


def _failure_check(message: str) -> list[str]:
    """Build a portable, deterministic check that reports a detection failure."""
    return [sys.executable, "-c", "import sys; print(sys.argv[1]); raise SystemExit(1)", message]


def detect_checks(workspace: str) -> tuple[list[tuple[str, list[str]]], list[str]]:
    """Return safe argument-vector checks and detection warnings."""
    checks: list[tuple[str, list[str]]] = []
    warnings: list[str] = []

    projects = detect_projects(workspace)
    if "python" in projects:
        if _has_python_tests(workspace):
            checks.append(("python-tests", [sys.executable, "-m", "pytest", "-q"]))
        else:
            checks.append(("python-syntax", [sys.executable, "-m", "compileall", "-q", "."]))
            warnings.append("No Python tests detected; running syntax validation only.")

    if "node" in projects:
        scripts, metadata_error = _node_scripts(workspace)
        if metadata_error:
            checks.append(("node-config", _failure_check(metadata_error)))
            warnings.append(metadata_error + " Fix package.json before running Node verification.")
            scripts = None
        if scripts is None:
            pass
        else:
            invalid_scripts = [
                name for name in ("test", "lint", "build")
                if name in scripts and not (
                    isinstance(scripts[name], str) and scripts[name].strip()
                )
            ]
            if invalid_scripts:
                names = ", ".join(invalid_scripts)
                message = f"Invalid package.json scripts: {names} must be non-empty strings."
                checks.append(("node-config", _failure_check(message)))
                warnings.append(message + " Fix these scripts before running Node verification.")
                scripts = None
        if scripts is not None:
            test_script = scripts.get("test", "")
            if test_script and "no test specified" not in test_script.lower():
                checks.append(("node-tests", ["npm", "test"]))
            elif "lint" in scripts:
                checks.append(("node-lint", ["npm", "run", "lint"]))
                warnings.append("No Node.js test script detected; running lint only.")
            elif "build" in scripts:
                checks.append(("node-build", ["npm", "run", "build"]))
                warnings.append("No Node.js test or lint script detected; running build only.")
            else:
                message = "Node.js project detected without a usable test, lint, or build script."
                checks.append(("node-config", _failure_check(message)))
                warnings.append(message + " Add one of these scripts to package.json.")

    if "rust" in projects:
        checks.append(("rust-tests", ["cargo", "test"]))
    if "go" in projects:
        checks.append(("go-tests", ["go", "test", "./..."]))

    for name, command in checks:
        executable = command[0]
        if os.path.isabs(executable):
            available = os.path.exists(executable)
        else:
            available = shutil.which(executable) is not None
        if not available:
            warnings.append(
                f"Cannot run {name}: executable not found: {executable}. "
                f"Install {executable} or provide an explicit command override."
            )

    return checks, warnings
