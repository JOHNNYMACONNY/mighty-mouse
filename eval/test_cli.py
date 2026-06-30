import json
import os
import shutil
import sys

import pytest
import yaml

from mighty_mouse import cli
from mighty_mouse.commands import benchmark_cmd, demo_cmd, doctor_cmd
from mighty_mouse.services import benchmark_service
from mighty_mouse.services.verifiers import adherence


def _run_cli(monkeypatch, *args):
    monkeypatch.setattr(sys, "argv", ["mighty-mouse", *args])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    return exc.value.code


def test_verify_passing_command_exits_zero(monkeypatch, tmp_path, capsys):
    code = _run_cli(
        monkeypatch,
        "verify",
        str(tmp_path),
        "--test-command",
        f'{sys.executable} -c "print(\'tests ran\')"',
    )

    assert code == 0
    output = capsys.readouterr().out
    assert "[PASS] tests" in output
    assert "tests ran" in output
    assert "Passed 1/1 verification checks." in output


def test_verify_failing_command_exits_one_with_suggestion(monkeypatch, tmp_path, capsys):
    code = _run_cli(
        monkeypatch,
        "verify",
        str(tmp_path),
        "--test-command",
        f'{sys.executable} -c "raise SystemExit(3)"',
    )

    assert code == 1
    output = capsys.readouterr().out
    assert "[FAIL] tests" in output
    assert "Suggestion: Fix the failing tests check" in output


def test_verify_invalid_workspace_exits_two(monkeypatch, tmp_path, capsys):
    code = _run_cli(monkeypatch, "verify", str(tmp_path / "missing"))

    assert code == 2
    assert "Workspace is not a directory" in capsys.readouterr().err


def test_verify_accepts_all_command_overrides(monkeypatch, tmp_path, capsys):
    command = f'{sys.executable} -c "pass"'
    code = _run_cli(
        monkeypatch,
        "verify",
        str(tmp_path),
        "--test-command", command,
        "--lint-command", command,
        "--build-command", command,
    )

    assert code == 0
    output = capsys.readouterr().out
    assert "[PASS] tests" in output
    assert "[PASS] lint" in output
    assert "[PASS] build" in output


def test_verify_repeatable_allowed_paths_check_scope(monkeypatch, tmp_path, capsys):
    import subprocess

    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "tracked.txt").write_text("original\n")
    subprocess.run(["git", "-C", str(tmp_path), "add", "tracked.txt"], check=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-qm", "initial"],
        check=True,
    )
    (tmp_path / "tracked.txt").write_text("changed\n")
    code = _run_cli(
        monkeypatch,
        "verify",
        str(tmp_path),
        "--test-command", f'{sys.executable} -c "pass"',
        "--allowed-path", "src/",
        "--allowed-path", "tracked.txt",
    )

    assert code == 0
    assert "[PASS] scope" in capsys.readouterr().out


def test_verify_timeout_fails_and_nonpositive_timeout_is_invalid(monkeypatch, tmp_path, capsys):
    code = _run_cli(
        monkeypatch,
        "verify",
        str(tmp_path),
        "--test-command", f'{sys.executable} -c "import time; time.sleep(2)"',
        "--timeout-sec", "1",
    )
    assert code == 1
    assert "Timed out after 1s" in capsys.readouterr().out

    code = _run_cli(monkeypatch, "verify", str(tmp_path), "--timeout-sec", "0")
    assert code == 2
    assert "must be a positive integer" in capsys.readouterr().err


def test_doctor_exits_zero(capsys):
    with pytest.raises(SystemExit) as exc:
        doctor_cmd.run_doctor(live=False)
    assert exc.value.code == 0
    assert "Doctor checks passed" in capsys.readouterr().out


def test_doctor_live_without_ollama(monkeypatch, capsys):
    monkeypatch.setattr(shutil, "which", lambda _: None)
    with pytest.raises(SystemExit) as exc:
        doctor_cmd.run_doctor(live=True)
    assert exc.value.code == 1
    assert "Ollama is not installed" in capsys.readouterr().out


def test_demo_sim_exits_zero(capsys):
    demo_cmd.run_demo()
    output = capsys.readouterr().out
    assert '"success_rate": "5/5"' in output
    assert "Recorded fixture replay" in output


def test_demo_live_requires_model():
    with pytest.raises(SystemExit) as exc:
        demo_cmd.run_demo(live=True)
    assert exc.value.code == 1


def test_demo_live_resolves_prompt_paths(monkeypatch, tmp_path):
    captured = {}

    def fake_benchmark(**kwargs):
        captured.update(kwargs)
        return {"summary": {"success_rate": "5/5"}, "output_dir": str(tmp_path)}

    monkeypatch.setattr(benchmark_service, "main", fake_benchmark)
    demo_cmd.run_demo(live=True, model="test-model", output_dir=str(tmp_path))

    config_path = captured["config_path"]
    with open(config_path, "r") as config_file:
        config = yaml.safe_load(config_file)

    assert config["model"] == "test-model"
    assert os.path.isabs(config["system_prompt_path"])
    assert all(os.path.isabs(path) for path in config["prompt_segments"])
    assert all(os.path.exists(path) for path in config["prompt_segments"])
    assert captured["output_dir"] == str(tmp_path)


def test_benchmark_no_tier_flag(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["mighty-mouse", "benchmark", "--tier", "foo"])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 2


def test_benchmark_missing_tasks_dir():
    with pytest.raises(SystemExit) as exc:
        benchmark_cmd.run_benchmark(tasks_dir="/definitely/missing/mighty-mouse-tasks")
    assert exc.value.code == 1


def test_benchmark_service_uses_output_dir(monkeypatch, tmp_path):
    task = tmp_path / "task.json"
    task.write_text(json.dumps({"id": "task"}))
    config = tmp_path / "config.yaml"
    config.write_text("provider: ollama\nmodel: test\nallow_simulation: false\n")

    def fake_run_task(*args):
        return {"status": "success", "latency_seconds": 0}

    class ImmediateExecutor:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def submit(self, fn, *args):
            class Result:
                def result(self):
                    return fake_run_task(*args)
            return Result()

    monkeypatch.setattr(benchmark_service.concurrent.futures, "ProcessPoolExecutor", ImmediateExecutor)
    monkeypatch.setattr(benchmark_service.concurrent.futures, "as_completed", lambda futures: futures)
    monkeypatch.setattr(benchmark_service.time, "sleep", lambda _: None)

    result = benchmark_service.main(
        tasks_list=[str(task)],
        config_path=str(config),
        max_workers=1,
        trials=1,
        output_dir=str(tmp_path / "output"),
    )

    assert result["output_dir"] == str(tmp_path / "output")
    assert os.path.exists(result["report_path"])


def test_run_task_materializes_task_inside_workspace(monkeypatch, tmp_path):
    task = tmp_path / "task.json"
    task.write_text(json.dumps({"id": "task", "expected_files": []}))
    config = tmp_path / "config.yaml"
    config.write_text("provider: ollama\nmodel: test\nallow_simulation: false\n")
    observed = {}

    def fake_subprocess_run(command, **kwargs):
        class Result:
            returncode = 0
            stdout = ""
            stderr = ""

        if command[1].endswith("sandbox_wrapper.py"):
            observed["verifier_task"] = command[-1]
            Result.stdout = json.dumps({"status": "success"})
        return Result()

    monkeypatch.setattr(benchmark_service.subprocess, "run", fake_subprocess_run)
    result = benchmark_service.run_task(
        str(task),
        config_path=str(config),
        trials=1,
        cleanup=False,
        output_dir=str(tmp_path / "output"),
    )

    verifier_task = observed["verifier_task"]
    assert verifier_task.startswith(str(tmp_path / "output" / "workspaces"))
    assert os.path.exists(verifier_task)
    assert result["status"] == "success"


def test_adherence_uses_installed_package_path(monkeypatch, tmp_path):
    checklist = tmp_path / "CHECKLIST.md"
    checklist.write_text("# Checklist\n")
    observed = {}

    def fake_run(command, **kwargs):
        observed["script"] = command[1]

        class Result:
            returncode = 0
            stdout = "PASS"
            stderr = ""

        return Result()

    monkeypatch.setattr(adherence.subprocess, "run", fake_run)
    passed, _ = adherence.check_adherence(str(checklist))

    assert passed
    assert observed["script"].endswith("mighty_mouse/orchestrator/enforce_workflow.py")
    assert os.path.exists(observed["script"])
