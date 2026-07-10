import json

import pytest

from eval.run_local_model_study import _resolve_held_out_check_paths, load_corpus


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
