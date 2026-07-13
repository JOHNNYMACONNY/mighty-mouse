import json
import sys
import threading
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
    FreshHoldout,
    Generation,
    ImmutableStateStore,
    ModelIdentity,
    Mode,
    Pin,
    Policy,
    PromotionController,
    Preview,
    Promotion,
    Restriction,
    Rollback,
    Signal,
    Scope,
    TaskCategory,
    resolve_execution_profile,
    status_document,
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


def _eligible_successor(store, *, candidate_id="candidate-002", security=True):
    candidate = Candidate(
        candidate_id=candidate_id,
        policy=Policy(policy_id="policy-002", mode=Mode.CODING, version="2"),
        scope=_scope(),
        model_digest="sha256:exact-model",
        required_capabilities=frozenset({"tools"}),
        compatible_execution_profiles=frozenset({"codex-local"}),
    )
    store.append_candidate(candidate)
    store.append(EvidenceBundle("evidence-002", "experiment-002", "sha256:exact-model", "codex-local", "sha256:evidence"))
    store.append(Experiment(
        "experiment-002", "generation-002", "candidate-001", "sha256:exact-model", "codex-local",
        (candidate.candidate_id,), ("evidence-002",), ("sha256:evidence",), (),
        (("safety", True), ("security", security), ("provenance", True), ("integrity", True), ("freshness", True)), "v2", ExperimentOutcome.COMPLETED,
        ExperimentDecision.NOMINATE, candidate.candidate_id,
    ))
    store.append(FreshHoldout(candidate.candidate_id, _scope(), "sha256:exact-model", "codex-local", True))
    if security:
        store.append_eligible_successor(
            EligibleSuccessor(candidate, "experiment-002", "evidence-002"),
            model_identity=ModelIdentity("sha256:exact-model"),
            execution_profile=ExecutionProfile("codex-local", frozenset({"tools"})),
        )
    return candidate


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
    _eligible_successor(store)
    successor = next(record.value for record in reversed(store.records()) if isinstance(record.value, EligibleSuccessor))
    controller = PromotionController(store)

    selection = store.select_policy(
        scope=_scope(),
        model_identity=ModelIdentity(None),
        execution_profile=ExecutionProfile("codex-local", frozenset({"tools"})),
    )

    assert selection.source == "safe_baseline"
    assert selection.policy.policy_id == "safe-baseline-coding"
    assert selection.reason == "model identity is incomplete"


def test_eligibility_explains_all_required_gates_and_preview_never_activates(tmp_path):
    store = ImmutableStateStore(tmp_path)
    store.append_promotion(_promotion())
    candidate = _eligible_successor(store)
    identity = ModelIdentity("sha256:exact-model")
    profile = ExecutionProfile("codex-local", frozenset({"tools"}))

    eligibility = store.eligibility(
        candidate_id=candidate.candidate_id, scope=_scope(), model_identity=identity, execution_profile=profile,
    )
    assert eligibility.is_eligible
    assert dict(eligibility.gates) == {
        "experiment": True, "compatibility": True, "evidence": True, "safety": True,
        "security": True, "provenance": True, "integrity": True, "freshness": True, "scope": True,
    }

    before = store.select_policy(scope=_scope(), model_identity=identity, execution_profile=profile)
    preview = store.preview(
        Preview("preview-002", _scope(), candidate.candidate_id, "evidence-002", "sha256:exact-model", "codex-local"),
        model_identity=identity,
        execution_profile=profile,
    )
    after = store.select_policy(scope=_scope(), model_identity=identity, execution_profile=profile)
    document = status_document(tmp_path, _scope(), identity, profile)

    assert preview.source == "preview"
    assert preview.policy == candidate.policy
    assert before == after
    assert after.policy.policy_id == "policy-001"
    assert document["eligible_successors"] == [{
        "candidate_id": "candidate-002", "experiment_id": "experiment-002", "evidence_bundle_id": "evidence-002",
        "eligible": True,
        "gates": {"experiment": True, "compatibility": True, "evidence": True, "safety": True,
                  "security": True, "provenance": True, "integrity": True, "freshness": True, "scope": True},
    }]
    assert [entry["kind"] for entry in document["history"]] == ["champion", "preview"]


def test_pin_locks_only_the_chosen_champion_while_later_successors_remain_visible(tmp_path):
    store = ImmutableStateStore(tmp_path)
    store.append_promotion(_promotion())
    identity = ModelIdentity("sha256:exact-model")
    profile = ExecutionProfile("codex-local", frozenset({"tools"}))
    store.pin(Pin("pin-001", _scope(), "candidate-001", "sha256:exact-model", "codex-local"), model_identity=identity, execution_profile=profile)
    candidate = _eligible_successor(store)
    with pytest.raises(ValueError, match="blocked by a Pin"):
        store.append_promotion(Promotion(EligibleSuccessor(candidate, "experiment-002", "evidence-002"), "candidate-001", True))

    selection = store.select_policy(scope=_scope(), model_identity=identity, execution_profile=profile)
    document = status_document(tmp_path, _scope(), identity, profile)

    assert selection.policy.policy_id == "policy-001"
    assert selection.reason == "exact compatible pinned Champion"
    assert document["eligible_successors"][0]["candidate_id"] == candidate.candidate_id
    assert [entry["kind"] for entry in document["history"]] == ["champion", "pin"]


def test_preview_and_pin_cli_never_silently_activate_a_candidate(monkeypatch, tmp_path, capsys):
    store = ImmutableStateStore(tmp_path)
    store.append_promotion(_promotion())
    candidate = _eligible_successor(store)
    common = [
        "--state-dir", str(tmp_path), "--mode", "coding", "--repository", "JOHNNYMACONNY/mighty-mouse",
        "--task-category", "maintenance", "--model-class", "local-small", "--model-digest", "sha256:exact-model",
        "--execution-profile", "codex-local", "--capability", "tools", "--json",
    ]

    monkeypatch.setattr(sys, "argv", ["mighty-mouse", "pin", "candidate-001", *common])
    cli.main()
    assert json.loads(capsys.readouterr().out)["interface"] == "pin"

    monkeypatch.setattr(sys, "argv", ["mighty-mouse", "preview", candidate.candidate_id, "--evidence-bundle-id", "evidence-002", *common])
    cli.main()
    assert json.loads(capsys.readouterr().out) == {
        "candidate_id": "candidate-002", "interface": "preview", "policy_id": "policy-002", "selection_changed": False,
    }

    with pytest.raises(ValueError, match="blocked by a Pin"):
        store.append_promotion(Promotion(EligibleSuccessor(candidate, "experiment-002", "evidence-002"), "candidate-001", True))
    selection = store.select_policy(
        scope=_scope(), model_identity=ModelIdentity("sha256:exact-model"),
        execution_profile=ExecutionProfile("codex-local", frozenset({"tools"})),
    )
    assert selection.policy.policy_id == "policy-001"


def test_promotion_controller_requires_health_check_and_recovers_prior_champion(tmp_path):
    store = ImmutableStateStore(tmp_path)
    store.append_promotion(_promotion())
    _eligible_successor(store)
    successor = next(record.value for record in reversed(store.records()) if isinstance(record.value, EligibleSuccessor))
    identity = ModelIdentity("sha256:exact-model")
    profile = ExecutionProfile("codex-local", frozenset({"tools"}))
    controller = PromotionController(store)

    with pytest.raises(ValueError, match="health check"):
        controller.promote(successor, model_identity=identity, execution_profile=profile, health_check=lambda: False)

    promoted, notice = controller.promote(successor, model_identity=identity, execution_profile=profile, health_check=lambda: True)
    assert notice.action == "promoted"
    assert notice.candidate_id == "candidate-002"
    assert store.select_policy(scope=_scope(), model_identity=identity, execution_profile=profile).policy.policy_id == "policy-002"

    rollback_notice = controller.enforce_live_guards(scope=_scope(), model_identity=identity, execution_profile=profile, quality_guard=lambda: False, security_guard=lambda: True)
    assert rollback_notice.action == "rolled_back"
    assert store.select_policy(scope=_scope(), model_identity=identity, execution_profile=profile).policy.policy_id == "policy-001"
    assert [record.value.promotion_id for record in store.records() if isinstance(record.value, Rollback)] == [promoted.record_hash]


def test_promotion_refuses_an_experiment_missing_a_required_security_gate(tmp_path):
    store = ImmutableStateStore(tmp_path)
    store.append_promotion(_promotion())
    candidate = _eligible_successor(store, security=False)
    identity = ModelIdentity("sha256:exact-model")
    profile = ExecutionProfile("codex-local", frozenset({"tools"}))

    eligibility = store.eligibility(candidate_id=candidate.candidate_id, scope=_scope(), model_identity=identity, execution_profile=profile)
    assert not eligibility.is_eligible
    assert dict(eligibility.gates)["security"] is False
    with pytest.raises(ValueError, match="recorded Eligible Successor"):
        store.append_promotion(Promotion(EligibleSuccessor(candidate, "experiment-002", "evidence-002"), "candidate-001", True))


def test_concurrent_selection_never_observes_a_partial_promotion_record(tmp_path):
    store = ImmutableStateStore(tmp_path)
    store.append_promotion(_promotion())
    _eligible_successor(store)
    successor = next(record.value for record in reversed(store.records()) if isinstance(record.value, EligibleSuccessor))
    controller = PromotionController(store)
    identity = ModelIdentity("sha256:exact-model")
    profile = ExecutionProfile("codex-local", frozenset({"tools"}))
    failures = []
    started = threading.Event()

    def reader():
        started.set()
        for _ in range(200):
            try:
                selection = ImmutableStateStore(tmp_path).select_policy(scope=_scope(), model_identity=identity, execution_profile=profile)
                assert selection.policy.policy_id in {"policy-001", "policy-002"}
            except Exception as error:  # pragma: no cover - asserted below
                failures.append(error)

    thread = threading.Thread(target=reader)
    thread.start()
    started.wait()
    for _ in range(25):
        controller.promote(successor, model_identity=identity, execution_profile=profile, health_check=lambda: True)
    thread.join()
    assert failures == []


def test_promotion_controller_restricts_security_breach_and_never_reactivates_it(tmp_path):
    store = ImmutableStateStore(tmp_path)
    store.append_promotion(_promotion())
    _eligible_successor(store)
    successor = next(record.value for record in reversed(store.records()) if isinstance(record.value, EligibleSuccessor))
    identity = ModelIdentity("sha256:exact-model")
    profile = ExecutionProfile("codex-local", frozenset({"tools"}))
    controller = PromotionController(store)
    controller.promote(successor, model_identity=identity, execution_profile=profile, health_check=lambda: True)

    notice = controller.recover(scope=_scope(), model_identity=identity, execution_profile=profile, reason="verified_provenance_breach", security_breach=True)
    assert notice.action == "restricted_and_rolled_back"
    assert store.select_policy(scope=_scope(), model_identity=identity, execution_profile=profile).policy.policy_id == "policy-001"
    assert [record.value.reason for record in store.records() if isinstance(record.value, Restriction)] == ["verified_provenance_breach"]
    with pytest.raises(ValueError, match="restricted Champion"):
        controller.promote(successor, model_identity=identity, execution_profile=profile, health_check=lambda: True)
    with pytest.raises(ValueError, match="controlled"):
        controller.recover(scope=_scope(), model_identity=identity, execution_profile=profile, reason="raw user content")


def test_security_guard_failure_restricts_the_active_champion(tmp_path):
    store = ImmutableStateStore(tmp_path)
    store.append_promotion(_promotion())
    controller = PromotionController(store)
    notice = controller.enforce_live_guards(
        scope=_scope(), model_identity=ModelIdentity("sha256:exact-model"),
        execution_profile=ExecutionProfile("codex-local", frozenset({"tools"})),
        quality_guard=lambda: True, security_guard=lambda: False,
    )
    assert notice.action == "restricted_and_rolled_back"
    assert len([record for record in store.records() if isinstance(record.value, Restriction)]) == 1


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
        store.append(Restriction("restriction-001", _scope(), candidate.candidate_id, "sha256:exact-model", profile.profile_id, "verified_security_guard_failure")),
        store.append(Pin("pin-001", _scope(), candidate.candidate_id, "sha256:exact-model", profile.profile_id)),
        store.append(Preview("preview-001", _scope(), candidate.candidate_id, evidence.evidence_bundle_id, "sha256:exact-model", profile.profile_id)),
        store.append(Rollback("rollback-001", _scope(), "promotion-001", candidate.candidate_id, "sha256:exact-model", profile.profile_id, "user_requested")),
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
