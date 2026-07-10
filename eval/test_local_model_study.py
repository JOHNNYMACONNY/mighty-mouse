import json

import pytest

from eval.run_local_model_study import _resolve_held_out_check_paths, load_corpus, run_study_task
from mighty_mouse.experiments.local_agent import AgentBudget


def write_task(root, task_id, complexity):
    task_dir = root / task_id
    workspace = task_dir / "workspace"
    workspace.mkdir(parents=True)
    (workspace / "broken.py").write_text("raise RuntimeError('broken')\n")
    (task_dir / "task.json").write_text(json.dumps({
        "id": task_id,
        "description": "Fix the bounded fixture.",
        "complexity": complexity,
        "workspace_template": "workspace",
        "allowed_paths": ["broken.py"],
        "checks": {"tests": ["{python}", "-c", "raise SystemExit(1)"]},
    }))
    return f"{task_id}/task.json"


def test_corpus_requires_balanced_frozen_metadata(tmp_path):
    tasks = []
    for index in range(30):
        tasks.append({
            "path": write_task(tmp_path, f"task-{index}", ("low", "medium", "high")[index % 3]),
            "category": "coding" if index < 15 else "agentic",
            "complexity": ("low", "medium", "high")[index % 3],
            "repository": f"repo-{index % 3}",
            "language": "python" if index % 2 else "typescript",
        })
    corpus = {"schema_version": 1, "study_class": "scored", "tasks": tasks}
    corpus_path = tmp_path / "corpus.json"
    corpus_path.write_text(json.dumps(corpus))

    loaded, paths = load_corpus(corpus_path)

    assert loaded["study_class"] == "scored"
    assert len(paths) == 30


def test_corpus_rejects_underpowered_category_balance(tmp_path):
    corpus_path = tmp_path / "corpus.json"
    corpus_path.write_text(json.dumps({"schema_version": 1, "study_class": "scored", "tasks": []}))

    with pytest.raises(ValueError, match="at least 30"):
        load_corpus(corpus_path)


def test_held_out_check_paths_are_anchored_but_public_checks_are_unchanged(tmp_path):
    task_dir = tmp_path / "task"
    task_dir.mkdir()
    hidden = task_dir / "hidden" / "check.py"
    hidden.parent.mkdir()
    hidden.write_text("pass\n")
    task_path = task_dir / "task.json"
    task_path.write_text("{}")
    template = task_dir / "workspace"
    template.mkdir()
    task = {
        "checks": {"public": ["python", "test.py"]},
        "acceptance_checks": {"held_out": ["python", "../hidden/check.py"]},
    }

    resolved = _resolve_held_out_check_paths(task, template)

    assert resolved["checks"]["public"] == ["python", "test.py"]
    assert resolved["acceptance_checks"]["held_out"][1] == str(hidden)


def test_task_runner_hides_and_anchors_acceptance_checks_and_resumes(tmp_path, monkeypatch):
    task_dir = tmp_path / "task"
    workspace = task_dir / "workspace"
    hidden = task_dir / "hidden"
    workspace.mkdir(parents=True)
    hidden.mkdir()
    (workspace / "module.py").write_text("value = 0\n")
    hidden_check = hidden / "held_out.py"
    hidden_check.write_text("raise SystemExit(1)\n")
    task_path = task_dir / "task.json"
    task_path.write_text(json.dumps({
        "id": "resume-fixture",
        "description": "Fix the fixture.",
        "complexity": "low",
        "workspace_template": "workspace",
        "allowed_paths": ["module.py"],
        "checks": {"public": ["{python}", "-c", "raise SystemExit(1)"]},
        "acceptance_checks": {"held_out": ["{python}", "../hidden/held_out.py"]},
    }))
    calls = []

    class FakeClient:
        def __init__(self, *args, **kwargs):
            calls.append(("client", args[0]))

    def fake_warmup(*args, **kwargs):
        return {"message": {}, "metrics": {}}

    def fake_run(_client, condition_workspace, task, *, condition, budget):
        calls.append(("run", condition))
        assert task["checks"]["public"][-1] == "raise SystemExit(1)"
        assert task["acceptance_checks"]["held_out"][1] == str(hidden_check)
        return {
            "model": "fake", "passed": True, "turns": 1, "tool_calls": 1,
            "duration_seconds": 1, "usage": {"total_tokens": 1}, "disallowed_changes": [],
        }

    monkeypatch.setattr("eval.run_local_model_study.OllamaChatClient", FakeClient)
    monkeypatch.setattr("eval.run_local_model_study._warm_model", fake_warmup)
    monkeypatch.setattr("eval.run_local_model_study.run_agent_condition", fake_run)
    manifest = {
        "corpus_digest": "test", "seed": 7,
        "model_by_condition": {key: "fake" for key in ("gemma_raw", "gemma_mighty_mouse", "reference_raw")},
        "budget": AgentBudget(max_turns=1, max_tool_calls=1, max_wall_seconds=30).__dict__,
    }

    first = run_study_task(task_path, tmp_path / "output", manifest=manifest, host="http://unused")
    second = run_study_task(task_path, tmp_path / "output", manifest=manifest, host="http://unused")

    assert first == second
    assert [call for call in calls if call[0] == "run"] == [("run", condition) for condition in first["condition_order"]]
