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
        "condition": condition,
        "first_try_pass": True,
        "retry_rounds": 0,
        "scope_violation": [],
        "duration_sec": 10.0,
        "quality_score": 4,
        "notes": "",
        "replace": False,
    }
    values.update(overrides)
    return Namespace(**values)


def _payload():
    return {"schema_version": 1, "status": "collecting", "minimum_paired_tasks": 10, "tasks": []}


def test_pair_requires_identical_pre_change_state():
    payload = update_results(_payload(), _args("control"))
    with pytest.raises(ValueError):
        update_results(payload, _args("harness", base_commit="different"))


def test_incomplete_study_makes_no_improvement_claim(tmp_path):
    payload = update_results(_payload(), _args("control"))
    payload = update_results(payload, _args("harness", first_try_pass=False))
    report = tmp_path / "report.md"
    write_report(payload, report)

    content = report.read_text()
    assert "1/10 minimum" in content
    assert "no generalized improvement claim" in content
    assert payload["status"] == "collecting"


def test_existing_evidence_file_is_valid_and_empty():
    payload = json.load(open("data/evidence/real_project_results.json"))
    assert payload["status"] == "collecting"
    assert payload["tasks"] == []
