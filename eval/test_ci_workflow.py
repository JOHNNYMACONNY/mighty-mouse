"""Semantic contract tests for the release-grade CI workflow."""

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"


def load_workflow():
    # PyYAML's YAML 1.1 loader treats the key ``on`` as a boolean. BaseLoader
    # preserves workflow keys and scalar versions exactly as authored.
    return yaml.load(WORKFLOW.read_text(), Loader=yaml.BaseLoader)


def step_named(job, name):
    return next(step for step in job["steps"] if step.get("name") == name)


def test_triggers_and_least_privilege_permissions():
    workflow = load_workflow()
    assert set(workflow["on"]) == {"push", "pull_request"}
    assert workflow["on"]["push"]["branches"] == ["main"]
    assert workflow["permissions"] == {"contents": "read"}


def test_complete_python_matrix_installs_both_packages_and_runs_full_suite():
    job = load_workflow()["jobs"]["test"]
    assert job["strategy"]["matrix"]["python-version"] == ["3.10", "3.11", "3.12", "3.13"]
    install = step_named(job, "Install both distributions and test dependencies")["run"]
    assert "-e '.[dev]'" in install
    assert "-e ./mcp" in install
    assert step_named(job, "Run complete test suite")["run"] == "python -m pytest"


def test_packaging_builds_and_installs_only_both_wheels():
    job = load_workflow()["jobs"]["package"]
    setup = next(step for step in job["steps"] if step.get("uses", "").startswith("actions/setup-python@"))
    assert setup["with"]["python-version"] == "3.13"

    build = step_named(job, "Build both wheels")["run"]
    assert "python -m build --wheel --outdir dist ." in build
    assert "python -m build --wheel --outdir dist ./mcp" in build

    install = step_named(job, "Install only built wheels in a clean environment")["run"]
    assert "python -m venv /tmp/" in install
    assert "pip install dist/mighty_mouse-*.whl dist/mighty_mouse_mcp-*.whl" in install
    assert "-e " not in install


def test_smokes_run_outside_checkout_and_cover_release_interfaces():
    step = step_named(load_workflow()["jobs"]["package"], "Smoke test installed wheels outside checkout")
    assert step["working-directory"] == "/tmp"
    smoke = step["run"]
    for required in (
        "import mighty_mouse",
        "mighty_mouse.__version__",
        "import mighty_mouse_mcp.server",
        "mighty_mouse_mcp.hooks",
        '"$CLI" --help',
        'mighty-mouse-signal-audit',
        'protocol "CI packaging smoke" --json',
        "json.load(sys.stdin)",
        "verify /tmp/mighty-mouse-verify-smoke",
        "--test-command",
        "d['passed'] is True",
    ):
        assert required in smoke


def test_official_actions_are_major_pinned_and_failures_are_not_suppressed():
    workflow = load_workflow()
    uses = [
        step["uses"]
        for job in workflow["jobs"].values()
        for step in job["steps"]
        if "uses" in step
    ]
    assert uses
    assert set(uses) <= {"actions/checkout@v4", "actions/setup-python@v5"}
    assert "continue-on-error" not in WORKFLOW.read_text()
