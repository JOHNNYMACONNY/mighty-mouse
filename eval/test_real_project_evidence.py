from argparse import Namespace
import json
from pathlib import Path

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


def test_complete_study_reports_mixed_result_without_claiming_general_improvement(tmp_path):
    payload = _payload()
    for index in range(10):
        task_id = f"real-{index:03d}"
        payload = update_results(payload, _args(
            "control",
            task_id=task_id,
            duration_sec=10 + index,
            quality_score=4,
            final_commit=f"control-{index}",
            artifact_dir=f"artifacts/{task_id}/control",
        ))
        payload = update_results(payload, _args(
            "harness",
            task_id=task_id,
            duration_sec=20 + index,
            quality_score=5,
            retry_rounds=1,
            final_commit=f"harness-{index}",
            artifact_dir=f"artifacts/{task_id}/harness",
        ))

    report = tmp_path / "report.md"
    write_report(payload, report)
    content = report.read_text()
    assert payload["status"] == "complete"
    assert "No generalized improvement was demonstrated" in content
    assert "First-try pass rate was tied" in content
    assert "Median duration (seconds)" in content
    assert "quality favored Mighty Mouse on 10 tasks" in content
    assert "completed faster on 0/10" in content


def test_existing_evidence_file_is_internally_consistent():
    payload = json.load(open("data/evidence/real_project_results.json"))
    assert payload["schema_version"] == 2
    paired = [task for task in payload["tasks"] if task["control"] and task["harness"]]
    assert payload["paired_tasks"] == len(paired)
    assert len({task["task_id"] for task in payload["tasks"]}) == len(payload["tasks"])
    expected_status = (
        "complete" if len(paired) >= payload["minimum_paired_tasks"] else "collecting"
    )
    assert payload["status"] == expected_status
    for task in paired:
        assert task["control"]["artifact_dir"] != task["harness"]["artifact_dir"]
        assert Path(task["control"]["artifact_dir"]).is_dir()
        assert Path(task["harness"]["artifact_dir"]).is_dir()

    report = Path("data/evidence/real_project_report.md").read_text()
    if expected_status == "collecting":
        assert "no generalized improvement claim is made" in report
    else:
        assert "No generalized improvement was demonstrated" in report
