import subprocess
from pathlib import Path

from mighty_mouse.services.verifiers.run_benchmark import verify_task
from mighty_mouse.verifier import verify


def _git_init(path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)


def test_task_fixture_flows_through_canonical_verifier_and_legacy_adapter(tmp_path: Path, monkeypatch) -> None:
    _git_init(tmp_path)
    task = {"id": "task-1", "expected_files": [], "test_script": "assert 2 + 2 == 4"}
    result = verify(str(tmp_path), task_config=task)
    assert result.passed
    assert [check.name for check in result.checks] == ["task-scope", "task-tests"]

    monkeypatch.chdir(tmp_path)
    legacy = verify_task(task, workspace=str(tmp_path))
    assert legacy["status"] == "success"
    assert legacy["scope"] == "PASS"


def test_task_fixture_failure_maps_to_legacy_result(tmp_path: Path) -> None:
    _git_init(tmp_path)
    task = {"id": "task-2", "expected_files": [], "test_script": "raise SystemExit(7)"}
    result = verify(str(tmp_path), task_config=task)
    assert not result.passed
    assert any(check.name == "task-tests" and not check.passed for check in result.checks)

