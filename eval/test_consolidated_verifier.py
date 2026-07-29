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


def test_verify_task_scope_clean():
    config = {"expected_files": []}
    passed, msg, telemetry = verify_task_scope(config)
    assert passed
    assert "Scope verified" in msg
    assert telemetry["scope_status"] == "PASS"


def test_verify_task_scope_unexpected_ghost_file(tmp_path, monkeypatch):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "unexpected_ghost.txt").write_text("ghost content")
    config = {"expected_files": ["allowed.py"]}
    passed, msg, telemetry = verify_task_scope(config)
    assert not passed
    assert "unexpected_ghost.txt" in telemetry["ghost_files_flagged_post_run"]


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


def test_services_verifiers_shims_compatibility():
    assert shim_scope.verify == verify_task_scope
    assert shim_adherence.check_adherence == check_adherence
    assert shim_tester.run_task_tests == run_task_tests
