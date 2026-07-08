import json

import pytest

from eval.analyze_local_model_study import analyze, load_summaries, render_markdown


def summary(task_id, raw, mighty, reference, study_class="scored"):
    return {
        "study_class": study_class,
        "task_id": task_id,
        "results": {
            "gemma_raw": {"passed": raw, "duration_seconds": 10, "total_tokens": 100, "tool_calls": 4},
            "gemma_mighty_mouse": {"passed": mighty, "duration_seconds": 12, "total_tokens": 120, "tool_calls": 5},
            "reference_raw": {"passed": reference, "duration_seconds": 8, "total_tokens": 90, "tool_calls": 3},
        },
    }


def test_analysis_calculates_paired_lift_and_gap_closure():
    result = analyze([
        summary("one", False, True, True),
        summary("two", False, False, True),
        summary("three", True, True, True),
        summary("four", False, True, False),
    ])

    assert result["conditions"]["gemma_raw"]["completion_rate"] == 0.25
    assert result["conditions"]["gemma_mighty_mouse"]["completion_rate"] == 0.75
    assert result["conditions"]["reference_raw"]["completion_rate"] == 0.75
    assert result["gemma_paired_outcomes"]["mighty_mouse_only"] == 2
    assert result["gemma_paired_outcomes"]["raw_only"] == 0
    assert result["gemma_paired_outcomes"]["completion_rate_difference"] == 0.5
    assert result["reference_gap"]["fraction_closed"] == 1.0
    assert result["claim_eligible"] is True


def test_gap_closure_is_undefined_without_a_positive_reference_gap():
    result = analyze([summary("one", True, True, True)])

    assert result["reference_gap"]["fraction_closed"] is None
    assert "not defined" in render_markdown(result)


def test_pilot_loading_requires_explicit_diagnostic_opt_in(tmp_path):
    run = tmp_path / "pilot"
    run.mkdir()
    (run / "summary.json").write_text(json.dumps(summary("pilot", True, True, True, "unscored_pilot")))

    with pytest.raises(ValueError, match="unscored"):
        load_summaries([run])
    loaded = load_summaries([run], allow_pilot=True)
    result = analyze(loaded)
    assert result["claim_eligible"] is False
    assert "not performance evidence" in render_markdown(result)


def test_loader_rejects_duplicate_tasks_and_missing_conditions(tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    payload = summary("duplicate", True, True, True)
    (first / "summary.json").write_text(json.dumps(payload))
    (second / "summary.json").write_text(json.dumps(payload))

    with pytest.raises(ValueError, match="duplicate"):
        load_summaries([first, second])

    payload["task_id"] = "missing"
    del payload["results"]["reference_raw"]
    (second / "summary.json").write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="missing conditions"):
        load_summaries([second])
