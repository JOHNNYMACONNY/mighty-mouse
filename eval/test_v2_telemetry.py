import pytest
from unittest.mock import Mock

from mighty_mouse.v2 import (
    PolicyLifecycle,
    PolicyState,
    TelemetryAggregator,
    resolve_effective_policy,
)
from mighty_mouse.v2.foundation import (
    ExecutionProfile,
    ImmutableStateStore,
    Mode,
    ModelIdentity,
    Policy,
    Scope,
    Signal,
    TaskCategory,
)
from perpetual_loop import AutoresearchLoop


@pytest.fixture
def store(tmp_path):
    return ImmutableStateStore(state_dir=str(tmp_path))


@pytest.fixture
def scope_a():
    return Scope(
        mode=Mode.CODING,
        repository="org/repo-a",
        task_category=TaskCategory.REFACTORING,
        model_class="local-small",
    )


@pytest.fixture
def scope_b():
    return Scope(
        mode=Mode.AGENTIC,
        repository="org/repo-b",
        task_category=TaskCategory.FEATURE,
        model_class="local-medium",
    )


def make_signal(signal_id: str, scope: Scope, outcome: str, duration_ms: int = 1000) -> Signal:
    return Signal(
        signal_id=signal_id,
        scope=scope,
        model_digest="sha256:0000000000000000000000000000000000000000000000000000000000000000",
        execution_profile_id="codex-local",
        outcome=outcome,
        duration_ms=duration_ms,
        retry_count=0,
        verifier_category="tests",
        verifier_result="passed" if outcome == "passed" else "failed",
    )


def test_telemetry_aggregator_empty_state(store, scope_a):
    aggregator = TelemetryAggregator(store=store)
    assert aggregator.compute_pass_rate(scope_a) is None
    summary = aggregator.get_telemetry_summary(scope_a)
    assert summary["pass_rate"] is None
    assert summary["total_signals"] == 0


def test_telemetry_aggregator_pass_rate_computation(store, scope_a, scope_b):
    aggregator = TelemetryAggregator(store=store)

    # Append 8 passed and 2 failed signals for scope_a
    for i in range(8):
        store.append(make_signal(f"signal-{i+100:03d}", scope_a, "passed", 500))
    for i in range(2):
        store.append(make_signal(f"signal-{i+108:03d}", scope_a, "failed", 1500))

    # Append 1 failed signal for scope_b
    store.append(make_signal("signal-200", scope_b, "failed", 2000))

    pass_rate_a = aggregator.compute_pass_rate(scope_a)
    assert pass_rate_a == 0.80

    summary_a = aggregator.get_telemetry_summary(scope_a)
    assert summary_a["pass_rate"] == 0.80
    assert summary_a["total_signals"] == 10
    assert summary_a["passed_signals"] == 8
    assert summary_a["failed_signals"] == 2
    assert summary_a["avg_duration_ms"] == (8 * 500 + 2 * 1500) / 10

    # Scope B isolated
    assert aggregator.compute_pass_rate(scope_b) == 0.0


def test_telemetry_aggregator_sliding_window(store, scope_a):
    aggregator = TelemetryAggregator(store=store, default_window_size=5)

    # Append 5 failed then 5 passed
    for i in range(5):
        store.append(make_signal(f"signal-{i+100:03d}", scope_a, "failed"))
    for i in range(5):
        store.append(make_signal(f"signal-{i+105:03d}", scope_a, "passed"))

    # Window of size 5 should only consider the last 5 signals (all passed -> 1.0)
    assert aggregator.compute_pass_rate(scope_a) == 1.0

    # Override window size to 10 (all 10 signals: 5 passed out of 10 -> 0.5)
    assert aggregator.compute_pass_rate(scope_a, window_size=10) == 0.5

    # Non-positive window sizes (0 or negative) should return None / default summary safely
    assert aggregator.compute_pass_rate(scope_a, window_size=0) is None
    assert aggregator.compute_pass_rate(scope_a, window_size=-5) is None
    assert aggregator.get_telemetry_summary(scope_a, window_size=0)["pass_rate"] is None
    assert aggregator.get_telemetry_summary(scope_a, window_size=-5)["pass_rate"] is None


def test_policy_lifecycle_with_telemetry_champion(store, scope_a):
    aggregator = TelemetryAggregator(store=store)
    # Add 9 passed signals (pass rate 0.90)
    for i in range(9):
        store.append(make_signal(f"signal-{i+100:03d}", scope_a, "passed"))
    store.append(make_signal("signal-109", scope_a, "failed"))

    lifecycle = PolicyLifecycle(store=store, telemetry_aggregator=aggregator)
    state = lifecycle.determine_state(scope_a)
    assert state == PolicyState.CHAMPION

    selection = lifecycle.resolve_policy(scope=scope_a)
    assert selection.source == "safe_baseline"


def test_policy_lifecycle_with_telemetry_degraded(store, scope_a):
    aggregator = TelemetryAggregator(store=store)
    # Add 6 passed and 4 failed (pass rate 0.60, between 0.50 and 0.75)
    for i in range(6):
        store.append(make_signal(f"signal-{i+100:03d}", scope_a, "passed"))
    for i in range(4):
        store.append(make_signal(f"signal-{i+106:03d}", scope_a, "failed"))

    lifecycle = PolicyLifecycle(store=store, telemetry_aggregator=aggregator)
    state = lifecycle.determine_state(scope_a)
    assert state == PolicyState.DEGRADED

    selection = lifecycle.resolve_policy(scope=scope_a)
    assert "degraded range" in selection.reason


def test_policy_lifecycle_with_telemetry_rollback(store, scope_a):
    aggregator = TelemetryAggregator(store=store)
    # Add 3 passed and 7 failed (pass rate 0.30, below 0.50)
    for i in range(3):
        store.append(make_signal(f"signal-{i+100:03d}", scope_a, "passed"))
    for i in range(7):
        store.append(make_signal(f"signal-{i+103:03d}", scope_a, "failed"))

    selection = resolve_effective_policy(scope=scope_a, store=store, telemetry_aggregator=aggregator)
    assert selection.source == "quality_degradation_rollback"
    assert "below threshold" in selection.reason


def test_autoresearch_loop_signal_recording(tmp_path, scope_a):
    loop = AutoresearchLoop(
        state_path=str(tmp_path / "state.json"),
        telemetry_path=str(tmp_path / "telemetry.json"),
        benchmark_results_path=str(tmp_path / "results.json"),
        mutation_engine=Mock(),
        state_dir=str(tmp_path),
    )
    loop.record_signal(scope=scope_a, outcome="passed", duration_ms=800, signal_counter=101)
    loop.record_signal(scope=scope_a, outcome="passed", duration_ms=900, signal_counter=102)

    pass_rate = loop.telemetry_aggregator.compute_pass_rate(scope_a)
    assert pass_rate == 1.0


def test_signal_count_for_scope_populated(store, scope_a, scope_b):
    aggregator = TelemetryAggregator(store=store)
    for i in range(5):
        store.append(make_signal(f"signal-{i+100:03d}", scope_a, "passed"))
    store.append(make_signal("signal-200", scope_b, "passed"))

    assert aggregator.signal_count_for_scope(scope_a) == 5
    assert aggregator.signal_count_for_scope(scope_b) == 1


def test_signal_count_for_scope_empty(store, scope_a):
    aggregator = TelemetryAggregator(store=store)
    assert aggregator.signal_count_for_scope(scope_a) == 0
