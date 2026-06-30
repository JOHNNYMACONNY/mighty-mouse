"""Contract tests for the release-grade GitHub Actions workflow."""

from copy import deepcopy
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "ci.yml"


class WorkflowLoader(yaml.SafeLoader):
    """Parse workflow keys using YAML 1.2 boolean behavior.

    PyYAML otherwise treats GitHub's ``on`` key as a YAML 1.1 boolean.
    """


WorkflowLoader.yaml_implicit_resolvers = deepcopy(yaml.SafeLoader.yaml_implicit_resolvers)
for first_character, resolvers in WorkflowLoader.yaml_implicit_resolvers.items():
    WorkflowLoader.yaml_implicit_resolvers[first_character] = [
        resolver for resolver in resolvers if resolver[0] != "tag:yaml.org,2002:bool"
    ]


def load_workflow():
    return yaml.load(WORKFLOW_PATH.read_text(encoding="utf-8"), Loader=WorkflowLoader)


def commands(job):
    return [step["run"] for step in job["steps"] if "run" in step]


def test_triggers_and_permissions_are_release_safe():
    workflow = load_workflow()

    assert set(workflow["on"]) == {"push", "pull_request"}
    assert workflow["on"]["push"]["branches"] == ["main"]
    assert workflow["permissions"] == {"contents": "read"}
    assert "continue-on-error" not in WORKFLOW_PATH.read_text(encoding="utf-8")


def test_complete_supported_python_matrix_runs_full_suite_with_mcp():
    test_job = load_workflow()["jobs"]["test"]
    matrix = test_job["strategy"]["matrix"]["python-version"]
    script = "\n".join(commands(test_job))

    assert matrix == ["3.10", "3.11", "3.12", "3.13"]
    assert "pip install -e \".[dev]\"" in script
    assert "pip install -e ./mcp" in script
    assert "python -m pytest -q" in script
    assert "--ignore" not in script and "-k " not in script


def test_packaging_builds_and_installs_only_both_wheels():
    package_job = load_workflow()["jobs"]["package"]
    script = "\n".join(commands(package_job))

    assert package_job["steps"][1]["with"]["python-version"] == "3.13"
    assert "python -m build --wheel --outdir dist/core ." in script
    assert "python -m build --wheel --outdir dist/mcp ./mcp" in script
    assert 'python -m venv "$RUNNER_TEMP/wheel-smoke"' in script
    assert "pip install dist/core/*.whl dist/mcp/*.whl" in script
    install_step = next(
        step for step in package_job["steps"] if step.get("name", "").startswith("Install only")
    )
    assert "-e " not in install_step["run"]


def test_packaging_smokes_all_public_surfaces_outside_checkout():
    package_job = load_workflow()["jobs"]["package"]
    smoke = next(step["run"] for step in package_job["steps"] if "Smoke-test" in step.get("name", ""))

    assert 'cd "$RUNNER_TEMP"' in smoke
    assert "import mighty_mouse; print(mighty_mouse.__version__)" in smoke
    assert "import mighty_mouse_mcp.server" in smoke
    assert 'bin/mighty-mouse\" --help' in smoke
    assert "protocol --complexity medium --json" in smoke
    assert "verify \"$RUNNER_TEMP\" --json --test-command" in smoke
    assert "print(\\\"ok\\\")" in smoke


def test_workflow_uses_only_pinned_official_actions_and_real_commands():
    workflow = load_workflow()
    uses = [
        step["uses"]
        for job in workflow["jobs"].values()
        for step in job["steps"]
        if "uses" in step
    ]

    assert set(uses) == {"actions/checkout@v4", "actions/setup-python@v5"}
    text = WORKFLOW_PATH.read_text(encoding="utf-8").lower()
    assert "todo" not in text and "placeholder" not in text
