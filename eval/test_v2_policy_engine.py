"""Tests for the deep PolicyEngine facade in Mighty Mouse v2."""

import pytest
from pathlib import Path

from mighty_mouse.v2.engine import PolicyEngine
from mighty_mouse.v2.foundation import ImmutableStateStore
from mighty_mouse.v2.records import (
    Mode,
    Scope,
    TaskCategory,
    ModelIdentity,
    ExecutionProfile,
    Policy,
    PolicySelection,
    Candidate,
    Signal,
    EvidenceBundle,
    FreshHoldout,
    EligibleSuccessor,
    Experiment,
    ExperimentOutcome,
    ExperimentDecision,
)


def test_state_store_selection_compatibility_delegates_to_policy_engine(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scope = Scope(
        Mode.CODING,
        "JOHNNYMACONNY/mighty-mouse",
        TaskCategory.FEATURE,
        "local-small",
    )
    model_id = ModelIdentity("sha256:" + "a" * 64)
    profile = ExecutionProfile("codex-local", frozenset({"test"}))
    expected = PolicySelection(
        policy=Policy("compatibility-policy", Mode.CODING, "test"),
        source="test",
        reason="compatibility seam",
        record_hash=None,
    )
    calls: list[tuple[Scope, ModelIdentity, ExecutionProfile]] = []

    def select_policy(self, scope, model_identity, execution_profile):
        calls.append((scope, model_identity, execution_profile))
        return expected

    monkeypatch.setattr(PolicyEngine, "select_policy", select_policy)

    selection = ImmutableStateStore(tmp_path).select_policy(
        scope=scope,
        model_identity=model_id,
        execution_profile=profile,
    )

    assert selection is expected
    assert calls == [(scope, model_id, profile)]


def test_status_selection_uses_policy_engine_seam(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scope = Scope(
        Mode.CODING,
        "JOHNNYMACONNY/mighty-mouse",
        TaskCategory.FEATURE,
        "local-small",
    )
    model_id = ModelIdentity("sha256:" + "a" * 64)
    profile = ExecutionProfile("codex-local", frozenset({"test"}))
    expected = PolicySelection(
        policy=Policy("status-policy", Mode.CODING, "test"),
        source="test",
        reason="status compatibility seam",
        record_hash=None,
    )
    calls: list[tuple[Scope, ModelIdentity, ExecutionProfile]] = []

    def select_policy(self, scope, model_identity, execution_profile):
        calls.append((scope, model_identity, execution_profile))
        return expected

    monkeypatch.setattr(PolicyEngine, "select_policy", select_policy)

    status = PolicyEngine(tmp_path).get_status(
        scope, model_id, profile
    )

    assert status["selection"]["policy_id"] == "status-policy"
    assert calls == [(scope, model_id, profile)]


def test_policy_engine_lifecycle(tmp_path: Path) -> None:
    engine = PolicyEngine(tmp_path)
    scope = Scope(Mode.CODING, "JOHNNYMACONNY/mighty-mouse", TaskCategory.FEATURE, "local-small")
    model_id = ModelIdentity("sha256:" + "a" * 64)
    profile = ExecutionProfile("sha256:" + "b" * 64, frozenset({"build", "test"}), "codex", "1.0", 8192, "sha256:" + "c" * 64, "sha256:" + "d" * 64)

    # 1. select_policy on empty store returns safe baseline
    selection = engine.select_policy(scope, model_id, profile)
    assert selection.policy.policy_id == "safe-baseline-coding"
    assert selection.source == "safe_baseline"

    # 2. record_signal
    sig = Signal("signal-001", scope, model_id.artifact_digest, profile.profile_id, "passed", 1500, 0, "tests", "passed")
    record = engine.record_signal(sig)
    assert record.record_hash is not None

    # 3. get_status
    status = engine.get_status(scope, model_id, profile)
    assert status["interface"] == "status"
    assert status["selection"]["policy_id"] == "safe-baseline-coding"
    assert status["history"] == []
