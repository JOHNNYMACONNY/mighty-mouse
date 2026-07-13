import json
import sys
from dataclasses import FrozenInstanceError

import pytest

from mighty_mouse import cli
from mighty_mouse.v2.foundation import (
    Candidate,
    Champion,
    EvidenceBundle,
    EligibleSuccessor,
    Experiment,
    ExperimentDecision,
    ExperimentOutcome,
    EvaluationOutcome,
    EvaluationOutcomeKind,
    ExecutionProfile,
    Generation,
    ImmutableStateStore,
    ModelIdentity,
    Mode,
    Pin,
    Policy,
    Preview,
    Promotion,
    Restriction,
    Rollback,
    Signal,
    Scope,
    TaskCategory,
    resolve_execution_profile,
)


def _scope():
    return Scope(
        mode=Mode.CODING,
        repository="JOHNNYMACONNY/mighty-mouse",
        task_category=TaskCategory.MAINTENANCE,
        model_class="local-small",
    )


def _candidate():
    return Candidate(
        candidate_id="candidate-001",
        policy=Policy(policy_id="policy-001", mode=Mode.CODING, version="1"),
        scope=_scope(),
        model_digest="sha256:exact-model",
        required_capabilities=frozenset({"tools"}),
        compatible_execution_profiles=frozenset({"codex-local"}),
    )


def _promotion():
    return Promotion(
        eligible_successor=EligibleSuccessor(
            candidate=_candidate(),
            experiment_id="experiment-001",
            evidence_bundle_id="evidence-001",
        ),
        prior_champion_id=None,
        machine_gates_passed=True,
    )


def test_immutable_store_selects_only_an_exactly_compatible_candidate(tmp_path):
    store = ImmutableStateStore(tmp_path)
    candidate = _candidate()

    stored = store.append_promotion(_promotion())
    selection = store.select_policy(
        scope=_scope(),
        model_identity=ModelIdentity("sha256:exact-model"),
        execution_profile=ExecutionProfile("codex-local", frozenset({"tools", "shell"})),
    )

    assert stored.record_hash
    assert selection.policy == candidate.policy
    assert selection.source == "project_improvement"
    assert selection.reason == "exact compatible Champion"
    assert selection.record_hash == stored.record_hash


def test_immutable_store_uses_safe_baseline_for_incomplete_or_incompatible_identity(tmp_path):
    store = ImmutableStateStore(tmp_path)
    store.append_promotion(_promotion())

    selection = store.select_policy(
        scope=_scope(),
        model_identity=ModelIdentity(None),
        execution_profile=ExecutionProfile("codex-local", frozenset({"tools"})),
    )

    assert selection.source == "safe_baseline"
    assert selection.policy.policy_id == "safe-baseline-coding"
    assert selection.reason == "model identity is incomplete"


def test_immutable_store_records_are_frozen_and_traceable(tmp_path):
    stored = ImmutableStateStore(tmp_path).append_candidate(_candidate())

    with pytest.raises(FrozenInstanceError):
        stored.value.candidate_id = "changed"

    document = json.loads((tmp_path / "v2-state.jsonl").read_text())
    assert document["schema_version"] == ImmutableStateStore.schema_version
    assert document["record_hash"] == stored.record_hash
    assert document["previous_record_hash"] is None


def test_status_cli_is_read_only_and_reports_the_selected_policy(monkeypatch, tmp_path, capsys):
    store = ImmutableStateStore(tmp_path)
    store.append_promotion(_promotion())
    state_before = (tmp_path / "v2-state.jsonl").read_bytes()
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "mighty-mouse",
            "status",
            "--state-dir",
            str(tmp_path),
            "--mode",
            "coding",
            "--repository",
            "JOHNNYMACONNY/mighty-mouse",
            "--task-category",
            "maintenance",
            "--model-class",
            "local-small",
            "--model-digest",
            "sha256:exact-model",
            "--execution-profile",
            "codex-local",
            "--capability",
            "tools",
            "--json",
        ],
    )

    cli.main()

    document = json.loads(capsys.readouterr().out)
    assert document["interface"] == "status"
    assert document["selection"]["source"] == "project_improvement"
    assert document["selection"]["policy_id"] == "policy-001"
    assert document["selection"]["record_pointer"].endswith(store.records()[-1].record_hash)
    assert (tmp_path / "v2-state.jsonl").read_bytes() == state_before


def test_immutable_store_round_trips_every_phase_a_record_type(tmp_path):
    store = ImmutableStateStore(tmp_path)
    candidate = _candidate()
    profile = resolve_execution_profile(
        runtime_kind="codex",
        runtime_version="1.0",
        effective_context_limit=32_000,
        tool_contract_digest="sha256:tools",
        prompt_template_digest="sha256:prompt",
        sampling_settings={"temperature": 0},
        resource_limits={"max_tool_calls": 10},
        capabilities={"tools"},
    )
    signal = Signal(
        signal_id="signal-001",
        scope=_scope(),
        model_digest="sha256:" + "a" * 64,
        execution_profile_id=profile.profile_id,
        outcome="passed",
        duration_ms=123,
        retry_count=0,
        verifier_category="tests",
    )
    evidence = EvidenceBundle(
        evidence_bundle_id="evidence-001",
        experiment_id="experiment-001",
        model_digest="sha256:exact-model",
        execution_profile_id=profile.profile_id,
        bundle_digest="sha256:evidence",
    )
    experiment = Experiment(
        experiment_id="experiment-001",
        generation_id="generation-001",
        baseline_candidate_id="baseline-001",
        model_digest="sha256:exact-model",
        execution_profile_id=profile.profile_id,
        candidate_ids=(candidate.candidate_id,),
        evidence_bundle_ids=(evidence.evidence_bundle_id,),
        evidence_bundle_digests=(evidence.bundle_digest,),
        evaluation_outcomes=(EvaluationOutcome("task-001", candidate.candidate_id, EvaluationOutcomeKind.PASSED),),
        gate_results=(("integrity", True),),
        protocol_version="v1",
        outcome=ExperimentOutcome.COMPLETED,
        decision=ExperimentDecision.NOMINATE,
        holdout_nominee_id=candidate.candidate_id,
    )
    generation = Generation(
        generation_id="generation-001",
        base_champion_id="champion-001",
        scope=_scope(),
        model_digest="sha256:exact-model",
        execution_profile_id=profile.profile_id,
        compatible_execution_profile_ids=(profile.profile_id,),
        signal_ids=(signal.signal_id,),
        signal_aggregate_digest="sha256:signals",
        experiment_ids=(experiment.experiment_id,),
        candidate_ids=(candidate.candidate_id,),
        protocol_version="v1",
        mutation_budget=1,
        seed_schedule=(7,),
        task_order=("task-001",),
        condition_order=("baseline", candidate.candidate_id),
    )
    promotion = _promotion()
    records = (
        store.append_champion(Champion("champion-001", candidate.candidate_id, _scope(), "sha256:exact-model", profile.profile_id)),
        store.append_candidate(candidate),
        store.append(signal),
        store.append(evidence),
        store.append(experiment),
        store.append(generation),
        store.append_promotion(promotion),
        store.append(Restriction("restriction-001", _scope(), candidate.candidate_id, "sha256:exact-model", profile.profile_id, "guard_failure")),
        store.append(Pin("pin-001", _scope(), candidate.candidate_id, "sha256:exact-model", profile.profile_id)),
        store.append(Preview("preview-001", _scope(), candidate.candidate_id, evidence.evidence_bundle_id, "sha256:exact-model", profile.profile_id)),
        store.append(Rollback("rollback-001", _scope(), "promotion-001", candidate.candidate_id, "sha256:exact-model", profile.profile_id, "manual")),
    )

    restored = store.records()

    assert [type(record.value) for record in restored] == [type(record.value) for record in records]
    assert len({record.record_hash for record in restored}) == len(restored)
    assert all(record.schema_version == ImmutableStateStore.schema_version for record in restored)


def test_execution_profile_resolver_is_canonical_and_changes_with_execution_contract():
    common = dict(
        runtime_kind="codex",
        runtime_version="1.0",
        effective_context_limit=32_000,
        tool_contract_digest="sha256:tools",
        prompt_template_digest="sha256:prompt",
        sampling_settings={"temperature": 0, "top_p": 1},
        resource_limits={"max_tool_calls": 10},
        capabilities={"tools", "structured_output"},
    )

    first = resolve_execution_profile(**common)
    reordered = resolve_execution_profile(**{**common, "sampling_settings": {"top_p": 1, "temperature": 0}})
    changed = resolve_execution_profile(**{**common, "runtime_version": "1.1"})

    assert first == reordered
    assert first.profile_id.startswith("sha256:")
    assert changed.profile_id != first.profile_id


def test_experiment_and_generation_reject_invalid_frozen_contracts():
    with pytest.raises(ValueError, match="no_change"):
        Experiment(
            "experiment-001", "generation-001", "baseline-001", "sha256:model", "sha256:profile",
            ("candidate-001",), ("evidence-001",), ("sha256:evidence",), (), (), "v1",
            ExperimentOutcome.COMPLETED, ExperimentDecision.NO_CHANGE, "candidate-001",
        )

    with pytest.raises(ValueError, match="must include its resolved profile"):
        Generation(
            "generation-001", None, _scope(), "sha256:model", "sha256:profile", (), (),
            "sha256:signals", (), (), "v1", 1, (), (), (),
        )
