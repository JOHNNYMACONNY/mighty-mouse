import pytest
from dataclasses import replace

from mighty_mouse.v2.evaluation import DevelopmentEvaluator, EvaluationRequest, EvaluationRun, FreshHoldoutEvaluator, FreshHoldoutRequest
from mighty_mouse.v2.foundation import Candidate, EvaluationOutcomeKind, ImmutableStateStore, Policy
from test_v2_background_research import _controller, _start


def _generation(tmp_path):
    controller = _controller(tmp_path)
    generation_id = _start(controller)["generation_id"]
    controller.run(thermal_state="normal")
    return generation_id


def _request(tmp_path, generation_id, capability=True, sandbox=True):
    base = tmp_path / "base"
    base.mkdir(parents=True, exist_ok=True)
    (base / "same-base.txt").write_text("frozen")
    return EvaluationRequest(generation_id, base, "sha256:preparation", "sha256:budget", capability, sandbox)


def test_development_evaluation_nominates_a_valid_paired_winner(tmp_path):
    generation_id = _generation(tmp_path)

    def runner(task_id, candidate, workspace, seed):
        assert workspace.exists()
        return EvaluationOutcomeKind.PASSED if candidate.policy.version == "generated-1" else EvaluationOutcomeKind.FAILED

    result = DevelopmentEvaluator(tmp_path).evaluate(_request(tmp_path, generation_id), runner)

    assert result.decision.value == "nominate"
    assert result.holdout_nominee_id


def test_fresh_holdout_is_quarantined_and_persists_only_its_gate(tmp_path):
    generation_id = _generation(tmp_path)
    result = DevelopmentEvaluator(tmp_path).evaluate(
        _request(tmp_path, generation_id), lambda task, candidate, workspace, seed: EvaluationOutcomeKind.PASSED if candidate.policy.version == "generated-1" else EvaluationOutcomeKind.FAILED
    )
    request = FreshHoldoutRequest(result.experiment_id, result.holdout_nominee_id, _request(tmp_path, generation_id).base_workspace, ("fresh-task-001",), "sha256:protocol", "sha256:environment", "sha256:corpus")
    held = FreshHoldoutEvaluator(tmp_path).evaluate(request, lambda *_: EvaluationOutcomeKind.PASSED)
    assert held.passed
    with pytest.raises(ValueError, match="ineligible"):
        FreshHoldoutRequest(result.experiment_id, result.holdout_nominee_id, request.base_workspace, request.task_ids, request.protocol_digest, request.environment_digest, request.corpus_digest, contaminated=True)


def test_development_evaluation_records_no_change_for_a_tie(tmp_path):
    generation_id = _generation(tmp_path)

    result = DevelopmentEvaluator(tmp_path).evaluate(
        _request(tmp_path, generation_id), lambda *_: EvaluationOutcomeKind.PASSED
    )

    assert result.decision.value == "no_change"
    assert result.holdout_nominee_id is None


def test_development_evaluation_is_invalid_when_a_gate_or_task_is_invalid(tmp_path):
    generation_id = _generation(tmp_path)

    result = DevelopmentEvaluator(tmp_path).evaluate(
        _request(tmp_path, generation_id, capability=False), lambda *_: EvaluationOutcomeKind.PASSED
    )

    assert result.outcome.value == "invalid"
    assert result.decision.value == "no_change"


def test_development_evaluation_rejects_a_second_nomination(tmp_path):
    generation_id = _generation(tmp_path)
    evaluator = DevelopmentEvaluator(tmp_path)
    runner = lambda task_id, candidate, workspace, seed: EvaluationOutcomeKind.PASSED if candidate.policy.version == "generated-1" else EvaluationOutcomeKind.FAILED
    evaluator.evaluate(_request(tmp_path, generation_id), runner)

    with pytest.raises(ValueError, match="at most one"):
        evaluator.evaluate(_request(tmp_path, generation_id), runner)


def test_development_evaluation_records_runner_errors_and_uses_efficiency_then_stability(tmp_path):
    generation_id = _generation(tmp_path)
    evaluator = DevelopmentEvaluator(tmp_path)
    def failing_runner(*_):
        raise RuntimeError("boom")
    assert evaluator.evaluate(_request(tmp_path, generation_id), failing_runner).outcome.value == "failed"

    generation_id = _generation(tmp_path / "second")
    def ranked_runner(task_id, candidate, workspace, seed):
        assert (workspace / "same-base.txt").read_text() == "frozen"
        if candidate.policy.version == "generated-1":
            return EvaluationRun(EvaluationOutcomeKind.PASSED, duration_ms=1, tool_calls=1, retries=0)
        return EvaluationRun(EvaluationOutcomeKind.PASSED, duration_ms=5, tool_calls=5, retries=2)
    assert evaluator.__class__(tmp_path / "second").evaluate(_request(tmp_path / "second", generation_id), ranked_runner).decision.value == "nominate"


@pytest.mark.parametrize("kind", [EvaluationOutcomeKind.ERROR, EvaluationOutcomeKind.TIMEOUT])
def test_candidate_runner_errors_are_ineligible_without_failing_the_experiment(tmp_path, kind):
    generation_id = _generation(tmp_path)

    def runner(task_id, candidate, workspace, seed):
        return EvaluationOutcomeKind.PASSED if candidate.policy.version == "1" else kind

    result = DevelopmentEvaluator(tmp_path).evaluate(_request(tmp_path, generation_id), runner)

    assert result.outcome.value == "completed"
    assert result.decision.value == "no_change"
    assert result.holdout_nominee_id is None


@pytest.mark.parametrize("kind", [EvaluationOutcomeKind.ERROR, EvaluationOutcomeKind.TIMEOUT])
def test_base_champion_runner_errors_fail_the_experiment(tmp_path, kind):
    generation_id = _generation(tmp_path)

    def runner(task_id, candidate, workspace, seed):
        return kind if candidate.policy.version == "1" else EvaluationOutcomeKind.PASSED

    result = DevelopmentEvaluator(tmp_path).evaluate(_request(tmp_path, generation_id), runner)

    assert result.outcome.value == "failed"
    assert result.decision.value == "no_change"
    assert result.holdout_nominee_id is None


def test_evaluation_runs_every_candidate_and_does_not_break_a_tie_by_identifier(tmp_path):
    generation_id = _generation(tmp_path)
    store = ImmutableStateStore(tmp_path)
    records = store.records()
    generation = next(record.value for record in reversed(records) if record.value.generation_id == generation_id)
    first_candidate = next(record.value for record in records if isinstance(record.value, Candidate) and record.value.candidate_id == generation.candidate_ids[0])
    second_candidate = replace(first_candidate, candidate_id="candidate-second", policy=Policy("policy-second", first_candidate.policy.mode, "generated-2"))
    store.append_candidate(second_candidate)
    store.append(replace(generation, candidate_ids=(first_candidate.candidate_id, second_candidate.candidate_id)))
    seen = []

    def tied_runner(task_id, candidate, workspace, seed):
        seen.append(candidate.candidate_id)
        return EvaluationOutcomeKind.FAILED if candidate.policy.version == "1" else EvaluationOutcomeKind.PASSED

    result = DevelopmentEvaluator(tmp_path).evaluate(_request(tmp_path, generation_id), tied_runner)

    assert seen.count("candidate-base") == 2
    assert seen.count(first_candidate.candidate_id) == 1
    assert seen.count(second_candidate.candidate_id) == 1
    assert result.decision.value == "no_change"
    experiment = next(record.value for record in reversed(store.records()) if record.value.experiment_id == result.experiment_id)
    assert {outcome.kind for outcome in experiment.evaluation_outcomes} == {EvaluationOutcomeKind.PASSED, EvaluationOutcomeKind.FAILED}


def test_timeout_is_recorded_as_an_error_with_a_machine_readable_reason(tmp_path):
    generation_id = _generation(tmp_path)
    result = DevelopmentEvaluator(tmp_path).evaluate(
        _request(tmp_path, generation_id),
        lambda task_id, candidate, workspace, seed: EvaluationOutcomeKind.TIMEOUT if candidate.policy.version != "1" else EvaluationOutcomeKind.PASSED,
    )

    experiment = next(record.value for record in reversed(ImmutableStateStore(tmp_path).records()) if record.value.experiment_id == result.experiment_id)
    candidate_outcome = next(outcome for outcome in experiment.evaluation_outcomes if outcome.candidate_id != "candidate-base")
    assert candidate_outcome.kind is EvaluationOutcomeKind.ERROR
    assert candidate_outcome.reason == "timeout"
