"""Conservative project-check auto-detection."""

from __future__ import annotations

import json
import os
import shutil
import sys
from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class DetectedCheck:
    name: str
    command: Sequence[str] | None
    error: str = ""


def _has_python_tests(workspace: str) -> bool:
    for root, dirs, files in os.walk(workspace):
        dirs[:] = [d for d in dirs if d not in {".git", ".venv", "node_modules"}]
        if any(name.startswith("test_") and name.endswith(".py") for name in files):
            return True
        if "tests" in dirs:
            return True
    return False


def _node_scripts(workspace: str) -> tuple[dict[str, str] | None, str]:
    package_path = os.path.join(workspace, "package.json")
    try:
        with open(package_path, encoding="utf-8") as package_file:
            package = json.load(package_file)
    except OSError as exc:
        return None, f"Unable to read package.json: {exc}"
    except json.JSONDecodeError as exc:
        return None, f"Invalid package.json: {exc.msg} (line {exc.lineno}, column {exc.colno})."
    if not isinstance(package, dict):
        return None, "Invalid package.json: top-level value must be an object."
    scripts = package.get("scripts", {})
    if not isinstance(scripts, dict):
        return None, "Invalid package.json: 'scripts' must be an object."
    return scripts, ""


def detect_checks(workspace: str) -> tuple[list[DetectedCheck], list[str], list[dict]]:
    """Return safe argument-vector checks and detection warnings."""
    checks: list[DetectedCheck] = []
    warnings: list[str] = []
    projects: list[dict] = []

    has_python = any(
        os.path.exists(os.path.join(workspace, marker))
        for marker in ("pyproject.toml", "setup.py", "setup.cfg")
    )
    if has_python:
        if _has_python_tests(workspace):
            check = DetectedCheck("python-tests", [sys.executable, "-m", "pytest", "-q"])
        else:
            check = DetectedCheck("python-syntax", [sys.executable, "-m", "compileall", "-q", "."])
            warnings.append("No Python tests detected; running syntax validation only.")
        checks.append(check)
        projects.append({"ecosystem": "python", "checks": [check.name], "status": "fallback" if check.name == "python-syntax" else "configured"})

    package_path = os.path.join(workspace, "package.json")
    if os.path.exists(package_path):
        scripts, metadata_error = _node_scripts(workspace)
        if metadata_error:
            warning = metadata_error + " Fix package.json before running Node.js verification."
            warnings.append(warning)
            check = DetectedCheck("node-metadata", None, metadata_error)
        else:
            assert scripts is not None
            test_script = str(scripts.get("test", ""))
            if test_script and "no test specified" not in test_script.lower():
                check = DetectedCheck("node-tests", ["npm", "test"])
            elif isinstance(scripts.get("lint"), str) and scripts["lint"].strip():
                check = DetectedCheck("node-lint", ["npm", "run", "lint"])
                warnings.append("No Node.js test script detected; running lint only.")
            elif isinstance(scripts.get("build"), str) and scripts["build"].strip():
                check = DetectedCheck("node-build", ["npm", "run", "build"])
                warnings.append("No Node.js test or lint script detected; running build only.")
            else:
                warning = "Node.js project detected without a usable test, lint, or build script. Add one to package.json."
                warnings.append(warning)
                check = DetectedCheck("node-configuration", None, warning)
        checks.append(check)
        projects.append({"ecosystem": "node", "checks": [check.name], "status": "configured" if check.command else "invalid"})

    if os.path.exists(os.path.join(workspace, "Cargo.toml")):
        checks.append(DetectedCheck("rust-tests", ["cargo", "test"]))
        projects.append({"ecosystem": "rust", "checks": ["rust-tests"], "status": "configured"})
    if os.path.exists(os.path.join(workspace, "go.mod")):
        checks.append(DetectedCheck("go-tests", ["go", "test", "./..."]))
        projects.append({"ecosystem": "go", "checks": ["go-tests"], "status": "configured"})

    final_checks = []
    for check in checks:
        if check.command is None:
            final_checks.append(check)
            continue
        name, command = check.name, check.command
        executable = command[0]
        if os.path.isabs(executable):
            available = os.path.exists(executable)
        else:
            available = shutil.which(executable) is not None
        if not available:
            warning = f"Cannot run {name}: executable not found: {executable}. Install it or provide an explicit command."
            warnings.append(warning)
            final_checks.append(DetectedCheck(name, None, warning))
            for project in projects:
                if name in project["checks"]:
                    project["status"] = "missing-tool"
        else:
            final_checks.append(check)

    return final_checks, warnings, projects
