import json
import os
import shutil
import sys

import pytest
import yaml

from mighty_mouse import cli
from mighty_mouse.commands import benchmark_cmd, demo_cmd, doctor_cmd
from mighty_mouse.commands import protocol_cmd, verify_cmd
from mighty_mouse.services import benchmark_service
from mighty_mouse.services.verifiers import adherence


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


def _run_cli(monkeypatch, command, *arguments):
    monkeypatch.setattr(sys, "argv", ["mighty-mouse", command, *arguments])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    return exc.value.code


def _run_verify_cli(monkeypatch, *arguments):
    return _run_cli(monkeypatch, "verify", *arguments)


def _run_protocol_cli(monkeypatch, *arguments):
    monkeypatch.setattr(sys, "argv", ["mighty-mouse", "protocol", *arguments])
    cli.main()
    return 0


def test_verify_cli_passes_and_renders_check(monkeypatch, tmp_path, capsys):
    command = f'{sys.executable} -c "print(\'verified\')"'

    assert _run_verify_cli(monkeypatch, str(tmp_path), "--test-command", command) == 0
    output = capsys.readouterr().out
    assert "PASS tests" in output
    assert "verified" in output


def test_verify_cli_fails_and_renders_suggestion(monkeypatch, tmp_path, capsys):
    command = f'{sys.executable} -c "raise SystemExit(3)"'

    assert _run_verify_cli(monkeypatch, str(tmp_path), "--test-command", command) == 1
    output = capsys.readouterr().out
    assert "FAIL tests" in output
    assert "Suggestions:" in output


def test_verify_cli_invalid_workspace_exits_two(monkeypatch, tmp_path, capsys):
    missing = tmp_path / "missing"

    assert _run_verify_cli(monkeypatch, str(missing)) == 2
    assert "Workspace is not a directory" in capsys.readouterr().err


def test_verify_cli_forwards_command_overrides_and_scope(monkeypatch, tmp_path, capsys):
    captured = {}

    def fake_verify(**kwargs):
        captured.update(kwargs)
        return type("Result", (), {
            "passed": True,
            "checks": [],
            "summary": "No checks failed.",
            "suggestions": [],
        })()

    monkeypatch.setattr(verify_cmd, "verify", fake_verify)
    code = _run_verify_cli(
        monkeypatch,
        str(tmp_path),
        "--test-command", "test override",
        "--lint-command", "lint override",
        "--build-command", "build override",
        "--allowed-path", "src/",
        "--allowed-path", "tests/",
    )

    assert code == 0
    assert captured["test_command"] == "test override"
    assert captured["lint_command"] == "lint override"
    assert captured["build_command"] == "build override"
    assert captured["allowed_paths"] == ["src/", "tests/"]
    assert "No checks failed." in capsys.readouterr().out


@pytest.mark.parametrize("value", ["0", "-1", "not-a-number"])
def test_verify_cli_rejects_invalid_timeout(monkeypatch, tmp_path, value):
    assert _run_verify_cli(
        monkeypatch, str(tmp_path), "--timeout-sec", value
    ) == 2


def test_verify_cli_timeout_fails_check(monkeypatch, tmp_path, capsys):
    command = f'{sys.executable} -c "import time; time.sleep(2)"'

    assert _run_verify_cli(
        monkeypatch,
        str(tmp_path),
        "--test-command", command,
        "--timeout-sec", "1",
    ) == 1
    output = capsys.readouterr().out.lower()
    assert "fail tests" in output
    assert "timed out" in output


@pytest.mark.parametrize(
    ("command", "expected_code", "expected_passed"),
    [
        (f'{sys.executable} -c "print(123)"', 0, True),
        (f'{sys.executable} -c "raise SystemExit(3)"', 1, False),
    ],
)
def test_verify_json_pass_and_failure(monkeypatch, tmp_path, capsys, command, expected_code, expected_passed):
    assert _run_verify_cli(monkeypatch, str(tmp_path), "--test-command", command, "--json") == expected_code
    captured = capsys.readouterr()
    document = json.loads(captured.out)
    assert captured.err == ""
    assert document["schema_version"] == 1
    assert document["interface"] == "verify"
    assert document["passed"] is expected_passed
    assert set(document) >= {"checks", "summary", "suggestions"}
    assert set(document["checks"][0]) >= {"name", "passed", "output", "duration_sec"}


def test_verify_json_invalid_workspace_exits_two(monkeypatch, tmp_path, capsys):
    assert _run_verify_cli(monkeypatch, str(tmp_path / "missing"), "--json") == 2
    captured = capsys.readouterr()
    document = json.loads(captured.out)
    assert captured.err == ""
    assert document == {
        "schema_version": 1,
        "interface": "verify",
        "passed": False,
        "checks": [],
        "summary": f"Workspace is not a directory: {tmp_path / 'missing'}",
        "suggestions": ["Provide a readable project workspace and run verification again."],
    }


@pytest.mark.parametrize("complexity", ["low", "medium", "high"])
def test_protocol_json_for_each_complexity(monkeypatch, capsys, complexity):
    task = f"Handle a {complexity} task"
    assert _run_protocol_cli(monkeypatch, task, "--complexity", complexity, "--json") == 0
    document = json.loads(capsys.readouterr().out)
    assert document["schema_version"] == 1
    assert document["interface"] == "protocol"
    assert document["task_description"] == task
    assert document["complexity"] == complexity
    assert document["protocol_prompt"].startswith("# Mighty Mouse v9.1")
    assert document["verification_reminder"] == protocol_cmd.VERIFICATION_REMINDER


def test_protocol_human_output_is_not_json(monkeypatch, capsys):
    assert _run_protocol_cli(monkeypatch, "Refactor the parser") == 0
    output = capsys.readouterr().out
    assert "Complexity: medium" in output
    assert "Selected protocol:" in output
    assert "# Mighty Mouse v9.1" in output
    assert "Verification reminder:" in output
    with pytest.raises(json.JSONDecodeError):
        json.loads(output)
