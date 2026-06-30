import json
import os
import subprocess
import sys

from mighty_mouse.verifier import verify


def _init_git(path):
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True)


def test_python_project_auto_detects_pytest(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='fixture'\nversion='0'\n")
    (tmp_path / "test_sample.py").write_text("def test_ok():\n    assert 2 + 2 == 4\n")

    result = verify(str(tmp_path))

    assert result.passed
    assert [check.name for check in result.checks] == ["python-tests"]


def test_node_project_auto_detects_npm_test(tmp_path):
    (tmp_path / "package.json").write_text(json.dumps({
        "scripts": {"test": f'"{sys.executable}" -c "print(123)"'}
    }))

    result = verify(str(tmp_path))

    assert result.passed
    assert result.checks[0].name == "node-tests"


def test_mixed_python_and_node_project_runs_both_suites(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='fixture'\nversion='0'\n")
    (tmp_path / "test_sample.py").write_text("def test_ok():\n    assert True\n")
    (tmp_path / "package.json").write_text(json.dumps({
        "scripts": {"test": f'"{sys.executable}" -c "print(123)"'}
    }))

    result = verify(str(tmp_path))

    assert result.passed
    assert [check.name for check in result.checks] == ["python-tests", "node-tests"]


def test_scope_flags_unapproved_change(tmp_path):
    _init_git(tmp_path)
    allowed = tmp_path / "src" / "allowed.py"
    allowed.parent.mkdir()
    allowed.write_text("value = 1\n")
    (tmp_path / "blocked.py").write_text("value = 1\n")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "fixture"], cwd=tmp_path, check=True)
    allowed.write_text("value = 2\n")
    (tmp_path / "blocked.py").write_text("value = 2\n")

    result = verify(
        str(tmp_path),
        test_command=[sys.executable, "-c", "pass"],
        allowed_paths=["src/allowed.py"],
    )

    assert not result.passed
    scope = next(check for check in result.checks if check.name == "scope")
    assert "blocked.py" in scope.output


def test_explicit_command_does_not_use_a_shell(tmp_path):
    marker = tmp_path / "shell-was-used"
    result = verify(
        str(tmp_path),
        test_command=f'{sys.executable} -c "print(\"safe\")" ; touch {marker}',
    )

    assert not marker.exists()
    assert not result.passed


def test_no_detected_checks_fails_with_actionable_suggestion(tmp_path):
    result = verify(str(tmp_path))

    assert not result.passed
    assert result.checks == []
    assert "explicit" in result.suggestions[-1]
