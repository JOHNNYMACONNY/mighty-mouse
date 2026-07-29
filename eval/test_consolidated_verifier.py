import os
import subprocess
import pytest

from mighty_mouse.verifier import verify
from mighty_mouse.verifier.scope import verify_task_scope, check_scope
from mighty_mouse.verifier.adherence import check_adherence
from mighty_mouse.verifier.tester import run_task_tests
from mighty_mouse.services.verifiers import (
    scope as shim_scope,
    adherence as shim_adherence,
    tester as shim_tester,
)


def test_check_scope_git_paths(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)

    allowed = tmp_path / "allowed.py"
    allowed.write_text("a = 1\n")
    blocked = tmp_path / "blocked.py"
    blocked.write_text("b = 1\n")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "initial"], cwd=tmp_path, check=True)

    allowed.write_text("a = 2\n")
    blocked.write_text("b = 2\n")

    passed, msg, violations = check_scope(str(tmp_path), ["allowed.py"])
    assert not passed
    assert "blocked.py" in violations


def test_verify_task_scope_clean():
    config = {"expected_files": []}
    passed, msg, signal = verify_task_scope(config)
    assert passed
    assert "Scope verified" in msg
    assert signal["scope_status"] == "PASS"


def test_verify_task_scope_unexpected_ghost_file(tmp_path, monkeypatch):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "unexpected_ghost.txt").write_text("ghost content")
    config = {"expected_files": ["allowed.py"]}
    passed, msg, signal = verify_task_scope(config, workspace=str(tmp_path))
    assert not passed
    assert "unexpected_ghost.txt" in signal["ghost_files_flagged_post_run"]


def test_check_adherence_missing():
    passed, msg = check_adherence("non_existent_checklist.md")
    assert not passed
    assert "not found" in msg


def test_run_task_tests(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    script = "import sys; sys.exit(0)\n"
    passed, logs = run_task_tests(script)
    assert passed


def test_verify_with_task_config(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='fixture'\nversion='0'\n")
    (tmp_path / "test_sample.py").write_text("def test_ok(): assert True\n")

    result = verify(str(tmp_path), task_config={"expected_files": []})
    assert result.passed
    check_names = [check.name for check in result.checks]
    assert "python-tests" in check_names
    assert "task-scope" in check_names


def test_verify_with_task_config_adherence(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='fixture'\nversion='0'\n")
    (tmp_path / "test_sample.py").write_text("def test_ok(): assert True\n")
    (tmp_path / "CHECKLIST.md").write_text("- [x] item\n")

    result = verify(str(tmp_path), task_config={"expected_files": [], "checklist_path": "CHECKLIST.md"})
    check_names = [check.name for check in result.checks]
    assert "task-adherence" in check_names


def test_services_verifiers_shims_compatibility():
    assert shim_scope.verify == verify_task_scope
    assert shim_adherence.check_adherence == check_adherence
    assert shim_tester.run_task_tests == run_task_tests
