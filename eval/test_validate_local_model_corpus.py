import json

import pytest

from eval.validate_local_model_corpus import validate_task


def make_task(root, *, solved_value="2"):
    workspace = root / "workspace"
    solution = root / "solution"
    hidden = root / "hidden"
    workspace.mkdir(parents=True)
    solution.mkdir()
    hidden.mkdir()
    (workspace / "value.py").write_text("VALUE = 1\n")
    (solution / "value.py").write_text(f"VALUE = {solved_value}\n")
    (hidden / "check.py").write_text(
        "import sys\nfrom pathlib import Path\nsys.path.insert(0, str(Path.cwd()))\nfrom value import VALUE\nassert VALUE == 2\n"
    )
    task = root / "task.json"
    task.write_text(json.dumps({
        "id": "validator-fixture", "description": "Fix the value.", "complexity": "low",
        "workspace_template": "workspace", "solution_template": "solution", "allowed_paths": ["value.py"],
        "checks": {"public": ["{python}", "-c", "raise SystemExit(1)"]},
        "acceptance_checks": {"held_out": ["{python}", "../hidden/check.py"]},
    }))
    return task


def test_validator_requires_failed_baseline_and_passing_solution(tmp_path):
    result = validate_task(make_task(tmp_path))

    assert result["baseline"] == {"held_out": False}
    assert result["solution"] == {"held_out": True}


def test_validator_rejects_a_bad_known_solution(tmp_path):
    with pytest.raises(ValueError, match="Known solution fails"):
        validate_task(make_task(tmp_path, solved_value="3"))
