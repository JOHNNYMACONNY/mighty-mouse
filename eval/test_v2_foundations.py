import json
import sys
from dataclasses import FrozenInstanceError

import pytest

from mighty_mouse import cli
from mighty_mouse.v2.foundation import (
    Candidate,
    EligibleSuccessor,
    ExecutionProfile,
    ImmutableStateStore,
    ModelIdentity,
    Mode,
    Policy,
    Promotion,
    Scope,
    TaskCategory,
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
    assert document["schema_version"] == 1
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
