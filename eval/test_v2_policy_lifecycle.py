import pytest

from mighty_mouse.v2 import PolicyState, PolicyLifecycle, resolve_effective_policy
from mighty_mouse.v2.foundation import (
    ExecutionProfile,
    ImmutableStateStore,
    ModelIdentity,
    Mode,
    Policy,
    PolicySelection,
    Scope,
    TaskCategory,
)


@pytest.fixture
def store(tmp_path):
    return ImmutableStateStore(state_dir=str(tmp_path))


@pytest.fixture
def scope():
    return Scope(
        mode=Mode.CODING,
        repository="test-repo",
        task_category=TaskCategory.REFACTORING,
        model_class="gemma",
    )


@pytest.fixture
def model_identity():
    return ModelIdentity(
        artifact_digest="sha256:abc123def4567890abc123def4567890abc123def4567890abc123def4567890",
    )


@pytest.fixture
def execution_profile():
    return ExecutionProfile(
        profile_id="ep-standard",
        capabilities=frozenset(["python", "git"]),
        runtime_kind="local",
    )


def test_determine_state_pinned(store, scope):
    pinned_policy = Policy(policy_id="pinned-001", mode=Mode.CODING, version="v1.0")
    lifecycle = PolicyLifecycle(
        store=store,
        pinned_policies={"coding": pinned_policy},
    )
    state = lifecycle.determine_state(scope)
    assert state == PolicyState.PINNED


def test_determine_state_rollback(store, scope):
    lifecycle = PolicyLifecycle(store=store, min_pass_rate_threshold=0.50)
    state = lifecycle.determine_state(scope, recent_pass_rate=0.30)
    assert state == PolicyState.ROLLBACK


def test_determine_state_degraded(store, scope):
    lifecycle = PolicyLifecycle(store=store, min_pass_rate_threshold=0.50, degraded_pass_rate_threshold=0.75)
    state = lifecycle.determine_state(scope, recent_pass_rate=0.65)
    assert state == PolicyState.DEGRADED


def test_determine_state_champion(store, scope):
    lifecycle = PolicyLifecycle(store=store)
    state = lifecycle.determine_state(scope, recent_pass_rate=0.85)
    assert state == PolicyState.CHAMPION


def test_resolve_policy_pinned(store, scope, model_identity, execution_profile):
    pinned_policy = Policy(policy_id="pinned-001", mode=Mode.CODING, version="v1.0")
    selection = resolve_effective_policy(
        scope=scope,
        store=store,
        model_identity=model_identity,
        execution_profile=execution_profile,
        pinned_policies={"coding": pinned_policy},
    )
    assert selection.policy == pinned_policy
    assert selection.source == "explicit_pinned_policy"


def test_resolve_policy_rollback(store, scope, model_identity, execution_profile):
    selection = resolve_effective_policy(
        scope=scope,
        store=store,
        model_identity=model_identity,
        execution_profile=execution_profile,
        recent_pass_rate=0.25,
    )
    assert selection.source == "quality_degradation_rollback"
    assert "safe-baseline-coding" in selection.policy.policy_id


def test_resolve_policy_champion_fallback(store, scope, model_identity, execution_profile):
    selection = resolve_effective_policy(
        scope=scope,
        store=store,
        model_identity=model_identity,
        execution_profile=execution_profile,
        recent_pass_rate=0.95,
    )
    assert selection.source == "safe_baseline"
    assert "safe-baseline-coding" in selection.policy.policy_id


def test_resolve_effective_policy_2_args(store, scope):
    selection = resolve_effective_policy(
        scope=scope,
        store=store,
    )
    assert selection.source == "safe_baseline"

