import json
from pathlib import Path

from eval import run_bare_baseline


def _task(path: Path):
    payload = {
        "id": "task_001",
        "title": "Fixture",
        "description": "Create result.py",
        "expected_files": ["result.py"],
        "test_script": "from result import value\nassert value == 42",
        "constraints": {"language": "python", "max_files": 1},
    }
    path.write_text(json.dumps(payload))


def test_bare_prompt_contains_no_harness_protocol(tmp_path):
    path = tmp_path / "task.json"
    _task(path)
    prompt = run_bare_baseline.build_prompt(json.loads(path.read_text()))

    assert "Mighty Mouse" not in prompt
    assert "<PLANNING>" not in prompt
    assert "CHECKLIST" not in prompt


def test_run_task_makes_exactly_one_generation_request(monkeypatch, tmp_path):
    task_path = tmp_path / "task.json"
    _task(task_path)
    calls = []

    def fake_request(prompt, model, host, timeout_sec):
        calls.append(prompt)
        return "```python:result.py\nvalue = 42\n```", {
            "latency_seconds": 1.0,
            "prompt_tokens": 10,
            "completion_tokens": 5,
        }

    monkeypatch.setattr(run_bare_baseline, "request_generation", fake_request)
    result = run_bare_baseline.run_task(
        task_path,
        tmp_path / "workspaces",
        "fixture-model",
        "http://localhost:11434",
        10,
    )

    assert len(calls) == 1
    assert result["status"] == "success"
    assert result["unexpected_files"] == []


def test_extra_generated_file_fails_scope(monkeypatch, tmp_path):
    task_path = tmp_path / "task.json"
    _task(task_path)

    def fake_request(*args):
        return "```python:result.py\nvalue = 42\n```\n```python:extra.py\npass\n```", {
            "latency_seconds": 1.0,
            "prompt_tokens": 10,
            "completion_tokens": 5,
        }

    monkeypatch.setattr(run_bare_baseline, "request_generation", fake_request)
    result = run_bare_baseline.run_task(
        task_path,
        tmp_path / "workspaces",
        "fixture-model",
        "http://localhost:11434",
        10,
    )

    assert result["status"] == "fail"
    assert result["unexpected_files"] == ["extra.py"]


def test_comparison_reads_the_lean_validation_report(tmp_path):
    rows = "\n".join(
        f"| task_{index:03}_fixture | success (10s) | success (8s) | 20% |"
        for index in range(1, 16)
    )
    (tmp_path / "validation_report.md").write_text(rows)
    results = {"results": [{"status": "success"}] * 15}
    output = tmp_path / "comparison.md"

    run_bare_baseline.write_comparison(results, tmp_path, output)

    report = output.read_text()
    assert "Original harness baseline | 15/15" in report
    assert "Lean harness | 15/15" in report
