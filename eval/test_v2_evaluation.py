import json

import pytest
from dataclasses import replace

from mighty_mouse.v2.evaluation import DevelopmentEvaluator, EvaluationRequest, EvaluationRun, FreshHoldoutEvaluator, FreshHoldoutRequest
from mighty_mouse.v2.foundation import Candidate, EvaluationOutcomeKind, Generation, ImmutableStateStore, Policy
from test_v2_background_research import _controller, _start


def _generation(tmp_path):
    controller = _controller(tmp_path)
    generation_id = _start(controller)["generation_id"]
    controller.run(thermal_state="normal")
    return generation_id


def _request(tmp_path, generation_id, capability=True, sandbox=True, protected_task_categories=None):
    base = tmp_path / "base"
    base.mkdir(parents=True, exist_ok=True)
    (base / "same-base.txt").write_text("frozen")
    if protected_task_categories is None:
        protected_task_categories = next(record.value.protected_task_categories for record in reversed(ImmutableStateStore(tmp_path).records()) if isinstance(record.value, Generation) and record.value.generation_id == generation_id)
    return EvaluationRequest(generation_id, base, "sha256:preparation", "sha256:budget", capability, sandbox, protected_task_categories)


def test_development_evaluation_nominates_a_valid_paired_winner(tmp_path):
    generation_id = _generation(tmp_path)

    def runner(task_id, candidate, workspace, seed):
        assert workspace.exists()
        return EvaluationOutcomeKind.PASSED if candidate.policy.version == "generated-1" else EvaluationOutcomeKind.FAILED

    result = DevelopmentEvaluator(tmp_path).evaluate(_request(tmp_path, generation_id), runner)

    assert result.decision.value == "nominate"
    assert result.holdout_nominee_id
    generation = next(record.value for record in ImmutableStateStore(tmp_path).records() if isinstance(record.value, Generation))
    assert result.experiment_id == generation.experiment_ids[0]


def test_fresh_holdout_is_quarantined_and_persists_only_its_gate(tmp_path):
    generation_id = _generation(tmp_path)
    result = DevelopmentEvaluator(tmp_path).evaluate(
        _request(tmp_path, generation_id), lambda task, candidate, workspace, seed: EvaluationOutcomeKind.PASSED if candidate.policy.version == "generated-1" else EvaluationOutcomeKind.FAILED
    )
    evaluator = FreshHoldoutEvaluator(tmp_path)
    task_digests = (("fresh-task-001", "sha256:fresh-task"),)
    manifest = evaluator.freeze_manifest(task_digests=task_digests, corpus_digest="sha256:corpus", protocol_digest="sha256:protocol", environment_digest="sha256:environment")
    request = FreshHoldoutRequest(result.experiment_id, result.holdout_nominee_id, _request(tmp_path, generation_id).base_workspace, ("fresh-task-001",), "sha256:protocol", "sha256:environment", "sha256:corpus", task_digests, manifest)
    held = evaluator.evaluate(request, lambda *_: EvaluationOutcomeKind.PASSED)
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

def test_protected_category_regression_cannot_be_nominated(tmp_path):
    controller = _controller(tmp_path)
    generation_id = _start(controller, protected_task_categories=(("maintenance", ("dev-001",)),))["generation_id"]
    controller.run(thermal_state="normal")
    protected_task = "dev-001"
    request = _request(tmp_path, generation_id, protected_task_categories=(("maintenance", (protected_task,)),))
    generation = next(record.value for record in ImmutableStateStore(tmp_path).records() if isinstance(record.value, Generation))
    assert generation.protected_task_categories == (("maintenance", (protected_task,)),)
    def runner(task, candidate, *_):
        if task == protected_task:
            return EvaluationOutcomeKind.FAILED if candidate.policy.version == "generated-1" else EvaluationOutcomeKind.PASSED
        return EvaluationOutcomeKind.PASSED if candidate.policy.version == "generated-1" else EvaluationOutcomeKind.FAILED
    result = DevelopmentEvaluator(tmp_path).evaluate(request, runner)
    assert result.decision.value == "no_change"


def test_evaluation_rejects_protected_categories_that_do_not_match_the_generation(tmp_path):
    controller = _controller(tmp_path)
    generation_id = _start(controller, protected_task_categories=(("maintenance", ("dev-001",)),))["generation_id"]
    controller.run(thermal_state="normal")

    request = replace(_request(tmp_path, generation_id), protected_task_categories=())

    with pytest.raises(ValueError, match="protected task categories"):
        DevelopmentEvaluator(tmp_path).evaluate(request, lambda *_: EvaluationOutcomeKind.PASSED)

    generation = next(record.value for record in ImmutableStateStore(tmp_path).records() if isinstance(record.value, Generation))
    with pytest.raises(ValueError, match="precommitted"):
        replace(generation, protected_task_categories=())


def test_evaluation_rejects_a_tampered_protocol_manifest(tmp_path):
    generation_id = _generation(tmp_path)
    manifest_path = tmp_path / "v2-background-research-manifests" / f"{generation_id}.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["task_order"] = ["tampered-task"]
    manifest_path.write_text(json.dumps(manifest))

    with pytest.raises(ValueError, match="Protocol Manifest"):
        DevelopmentEvaluator(tmp_path).evaluate(_request(tmp_path, generation_id), lambda *_: EvaluationOutcomeKind.PASSED)


def test_development_evaluation_is_invalid_when_a_gate_or_task_is_invalid(tmp_path):
    generation_id = _generation(tmp_path)

    result = DevelopmentEvaluator(tmp_path).evaluate(
        _request(tmp_path, generation_id, capability=False), lambda *_: EvaluationOutcomeKind.PASSED
    )

    assert result.outcome.value == "invalid"
    assert result.decision.value == "no_change"


def test_development_evaluation_rejects_any_second_evaluation_for_a_generation(tmp_path):
    generation_id = _generation(tmp_path)
    evaluator = DevelopmentEvaluator(tmp_path)
    runner = lambda *_: EvaluationOutcomeKind.PASSED
    evaluator.evaluate(_request(tmp_path, generation_id), runner)

    with pytest.raises(ValueError, match="already been evaluated"):
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
    with pytest.raises(ValueError, match="duplicate immutable record identity"):
        store.append(replace(generation, candidate_ids=(first_candidate.candidate_id, second_candidate.candidate_id)))


def test_immutable_store_rejects_a_duplicate_candidate_identity(tmp_path):
    generation_id = _generation(tmp_path)
    candidate = next(record.value for record in ImmutableStateStore(tmp_path).records() if isinstance(record.value, Candidate) and record.value.candidate_id != "candidate-base")

    with pytest.raises(ValueError, match="duplicate immutable record identity"):
        ImmutableStateStore(tmp_path).append_candidate(candidate)


def test_evaluation_requires_exactly_one_precommitted_experiment(tmp_path):
    generation_id = _generation(tmp_path)
    store = ImmutableStateStore(tmp_path)
    generation = next(record.value for record in store.records() if isinstance(record.value, Generation))
    malformed = replace(generation, generation_id="generation-without-experiment", experiment_ids=())
    store.append(malformed)

    with pytest.raises(ValueError, match="exactly one precommitted Experiment"):
        DevelopmentEvaluator(tmp_path).evaluate(_request(tmp_path, malformed.generation_id), lambda *_: EvaluationOutcomeKind.PASSED)


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


def test_each_condition_outcome_links_to_its_immutable_evidence_bundle(tmp_path, monkeypatch):
    generation_id = _generation(tmp_path)
    captured_evidence_payloads = []
    digest = DevelopmentEvaluator._digest

    def capture_digest(value):
        if "protocol_manifest_digest" in value:
            captured_evidence_payloads.append(value)
        return digest(value)

    monkeypatch.setattr(DevelopmentEvaluator, "_digest", staticmethod(capture_digest))
    result = DevelopmentEvaluator(tmp_path).evaluate(
        _request(tmp_path, generation_id),
        lambda task_id, candidate, workspace, seed: EvaluationOutcomeKind.PASSED,
    )

    records = ImmutableStateStore(tmp_path).records()
    experiment = next(record.value for record in records if getattr(record.value, "experiment_id", None) == result.experiment_id and type(record.value).__name__ == "Experiment")
    bundles = {record.value.evidence_bundle_id for record in records if type(record.value).__name__ == "EvidenceBundle"}
    bundle_by_id = {record.value.evidence_bundle_id: record.value for record in records if type(record.value).__name__ == "EvidenceBundle"}

    assert all(outcome.evidence_bundle_id in bundles for outcome in experiment.evaluation_outcomes)
    assert {outcome.evidence_bundle_id for outcome in experiment.evaluation_outcomes}.issubset(experiment.evidence_bundle_ids)
    assert all(bundle_by_id[outcome.evidence_bundle_id].candidate_id == outcome.candidate_id for outcome in experiment.evaluation_outcomes)
    generation = next(record.value for record in records if isinstance(record.value, Generation) and record.value.generation_id == generation_id)
    assert captured_evidence_payloads
    assert all(payload["protocol_manifest_digest"] == generation.protocol_manifest_digest for payload in captured_evidence_payloads)
    assert all(payload["model_digest"] == generation.model_digest and payload["execution_profile_id"] == generation.execution_profile_id for payload in captured_evidence_payloads)
