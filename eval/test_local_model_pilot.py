import json
import sys
from pathlib import Path

import pytest

from eval import run_local_model_pilot
from mighty_mouse.experiments.local_agent import AgentBudget


def write_task(root: Path) -> Path:
    template = root / "template"
    template.mkdir()
    (template / "value.py").write_text("VALUE = 0\n")
    task = root / "task.json"
    task.write_text(json.dumps({
        "id": "pilot-low",
        "description": "Set VALUE to 42.",
        "complexity": "low",
        "workspace_template": "template",
        "allowed_paths": ["value.py"],
        "ignored_paths": ["__pycache__"],
        "checks": {"tests": ["{python}", "-c", "from value import VALUE; assert VALUE == 42"]},
    }))
    return task


def test_load_task_resolves_template_and_python(tmp_path):
    task, template = run_local_model_pilot.load_task(write_task(tmp_path))

    assert template == (tmp_path / "template").resolve()
    assert task["checks"]["tests"][0] == sys.executable


def test_load_task_normalizes_separate_held_out_checks(tmp_path):
    task_path = write_task(tmp_path)
    payload = json.loads(task_path.read_text())
    payload["acceptance_checks"] = {"held_out": ["{python}", "-c", "assert True"]}
    task_path.write_text(json.dumps(payload))

    task, _ = run_local_model_pilot.load_task(task_path)

    assert task["checks"]["tests"][0] == sys.executable
    assert task["acceptance_checks"]["held_out"][0] == sys.executable


def test_pilot_uses_pristine_workspaces_and_records_all_conditions(monkeypatch, tmp_path):
    task_path = write_task(tmp_path)
    seen = []

    monkeypatch.setattr(
        run_local_model_pilot,
        "_model_provenance",
        lambda host, model: {"name": model, "digest": f"digest-{model}"},
    )

    def fake_run(client, workspace, task, *, condition, budget):
        seen.append((condition, client.model, (workspace / "value.py").read_text()))
        (workspace / "value.py").write_text("VALUE = 42\n")
        return {
            "model": client.model,
            "passed": True,
            "turns": 1,
            "tool_calls": 1,
            "duration_seconds": 0.1,
            "usage": {"total_tokens": 10},
            "disallowed_changes": [],
        }

    monkeypatch.setattr(run_local_model_pilot, "run_agent_condition", fake_run)
    monkeypatch.setattr(
        run_local_model_pilot,
        "_warm_model",
        lambda client, budget: {"message": {"content": "READY"}, "metrics": {"model": client.model}},
    )
    output = tmp_path / "run"
    summary = run_local_model_pilot.run_pilot(
        task_path,
        output,
        gemma_model="gemma-test",
        reference_model="reference-test",
        host="http://ollama.test",
        seed=7,
        budget=AgentBudget(max_turns=2, max_tool_calls=2, max_wall_seconds=30),
    )

    assert set(summary["results"]) == set(run_local_model_pilot.CONDITIONS)
    assert len(seen) == 3
    assert all(initial == "VALUE = 0\n" for _, _, initial in seen)
    assert {condition: model for condition, model, _ in seen} == {
        "gemma_raw": "gemma-test",
        "gemma_mighty_mouse": "gemma-test",
        "reference_raw": "reference-test",
    }
    assert json.loads((output / "run_manifest.json").read_text())["study_class"] == "unscored_pilot"
    assert json.loads((output / "baseline_checks.json").read_text())["tests"]["passed"] is False
    manifest = json.loads((output / "run_manifest.json").read_text())
    assert manifest["task_source"] == "task.json"
    assert str(tmp_path) not in json.dumps(manifest)
    frozen_task = json.loads((output / "task.json").read_text())
    assert frozen_task["workspace_template"] == "template"
    assert frozen_task["checks"]["tests"][0] == "{python}"
    assert str(tmp_path) not in json.dumps(frozen_task)
    assert json.loads((output / "summary.json").read_text()) == summary


def test_pilot_refuses_to_overwrite_existing_output(monkeypatch, tmp_path):
    task_path = write_task(tmp_path)
    output = tmp_path / "existing"
    output.mkdir()

    with pytest.raises(FileExistsError, match="Refusing to overwrite"):
        run_local_model_pilot.run_pilot(
            task_path,
            output,
            gemma_model="gemma-test",
            reference_model="reference-test",
            host="http://ollama.test",
            seed=7,
            budget=AgentBudget(max_turns=2, max_tool_calls=2, max_wall_seconds=30),
        )


def test_pilot_rejects_an_already_solved_task(monkeypatch, tmp_path):
    task_path = write_task(tmp_path)
    (tmp_path / "template" / "value.py").write_text("VALUE = 42\n")
    monkeypatch.setattr(
        run_local_model_pilot,
        "_model_provenance",
        lambda host, model: {"name": model, "digest": f"digest-{model}"},
    )

    with pytest.raises(ValueError, match="already solved"):
        run_local_model_pilot.run_pilot(
            task_path,
            tmp_path / "run",
            gemma_model="gemma-test",
            reference_model="reference-test",
            host="http://ollama.test",
            seed=7,
            budget=AgentBudget(max_turns=2, max_tool_calls=2, max_wall_seconds=30),
        )
