from argparse import Namespace
import json

import pytest

from eval.record_real_project_trial import update_results, write_report


def _args(condition, **overrides):
    values = {
        "task_id": "real-001",
        "project": "fixture",
        "task_description": "Fix the parser",
        "base_commit": "abc123",
        "agent": "codex-cli",
        "model": "gpt-test",
        "model_settings": "reasoning=medium",
        "environment_fingerprint": "sha256:environment",
        "timeout_sec": 900,
        "acceptance_command": ["pytest -q"],
        "allowed_path": ["src/parser.py", "eval/test_parser.py"],
        "condition": condition,
        "first_try_pass": True,
        "retry_rounds": 0,
        "scope_violation": [],
        "duration_sec": 10.0,
        "quality_score": 4,
        "final_commit": f"{condition}-commit",
        "artifact_dir": f"artifacts/real-001/{condition}",
        "review_rationale": "Correct and focused.",
        "notes": "",
        "replace": False,
    }
    values.update(overrides)
    return Namespace(**values)


def _payload():
    return {"schema_version": 2, "status": "collecting", "minimum_paired_tasks": 10, "tasks": []}


def test_pair_requires_identical_pre_change_state():
    payload = update_results(_payload(), _args("control"))
    with pytest.raises(ValueError):
        update_results(payload, _args("harness", base_commit="different"))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("agent", "another-agent"),
        ("model", "another-model"),
        ("model_settings", "reasoning=high"),
        ("environment_fingerprint", "sha256:different"),
        ("timeout_sec", 1200),
        ("acceptance_command", ["pytest -x"]),
        ("allowed_path", ["src/other.py"]),
    ],
)
def test_pair_requires_identical_shared_configuration(field, value):
    payload = update_results(_payload(), _args("control"))
    with pytest.raises(ValueError):
        update_results(payload, _args("harness", **{field: value}))


def test_incomplete_study_makes_no_improvement_claim(tmp_path):
    payload = update_results(_payload(), _args("control"))
    payload = update_results(payload, _args("harness", first_try_pass=False))
    report = tmp_path / "report.md"
    write_report(payload, report)

    content = report.read_text()
    assert "1/10 minimum" in content
    assert "no generalized improvement claim" in content
    assert "Mean duration (seconds)" in content
    assert "Mean quality (1–5)" in content
    assert "| real-001 | yes | no | 0/0 | 0/0 | 10.0/10.0 | 4/4 |" in content
    assert payload["status"] == "collecting"


def test_condition_provenance_is_retained():
    payload = update_results(_payload(), _args("control"))
    task = payload["tasks"][0]
    assert task["shared_config"]["agent"] == "codex-cli"
    assert task["shared_config"]["acceptance_commands"] == ["pytest -q"]
    assert task["control"]["final_commit"] == "control-commit"
    assert task["control"]["artifact_dir"] == "artifacts/real-001/control"


def test_existing_evidence_file_is_valid_and_empty():
    payload = json.load(open("data/evidence/real_project_results.json"))
    assert payload["schema_version"] == 2
    assert payload["status"] == "collecting"
    assert payload["tasks"] == []
