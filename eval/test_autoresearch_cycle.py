from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from eval.autoresearch_cycle import (
    AutoresearchCycle,
    CycleResult,
    MutationRequest,
)
from eval import perpetual_loop as perpetual_loop_module
from eval.perpetual_loop import (
    AutoresearchLoop,
    CycleResult as LoopCycleResult,
)
from eval.tier_utils import parse_pass_rate
from mighty_mouse.v2.seams import VerificationResult


def _state(*, mutation_count: int = 0) -> dict:
    return {
        "current_tier": "tier-1",
        "mutation_count": mutation_count,
        "total_iterations": 0,
        "history": [],
    }


def _verification(score: float) -> VerificationResult:
    return VerificationResult(
        passed=score >= 1.0,
        score=score,
        details={"verifier_category": "LOGIC"},
        verdict_category="PASS" if score >= 1.0 else "FAIL",
    )


class FakeCycleOperations:
    """Small behavioral collaborator for cycle state-machine tests."""

    def __init__(
        self,
        benchmark: dict | None,
        events: list[str],
        *,
        verifier_adapter=None,
        mutation_handler=None,
    ) -> None:
        self.benchmark = benchmark
        self.events = events
        self.verifier_adapter = verifier_adapter
        self.mutation_handler = mutation_handler or Mock()

    def config_hash(self) -> str:
        return "config-hash"

    def run_benchmark(self, _tier: str) -> dict | None:
        return self.benchmark

    def verify_benchmark(self, benchmark: dict) -> VerificationResult:
        if self.verifier_adapter is not None:
            return self.verifier_adapter(benchmark)
        return _verification(
            parse_pass_rate(benchmark.get("summary", {}))
        )

    def update_telemetry(
        self, _tier: str, _summary: dict, _config_hash: str
    ) -> None:
        self.events.append("telemetry")

    def record_signal(
        self, *, scope, outcome: str, signal_counter: int
    ) -> str:
        del scope, outcome, signal_counter
        self.events.append("signal")
        return "signal-1"

    def replay_tiers(self, _tier: str) -> list[str]:
        return ["tier-0"]

    def execute_mutation(
        self,
        request: MutationRequest,
    ):
        self.events.append("mutation")
        return self.mutation_handler(request)

    def save_state(self) -> None:
        self.events.append("save")

    def run_parity_report(self) -> None:
        self.events.append("parity")


def _cycle(
    state: dict,
    benchmark: dict | None,
    *,
    events: list[str],
    verifier_adapter=None,
    mutation_adapter=None,
    mutation_engine=None,
) -> AutoresearchCycle:
    mutation_handler = mutation_adapter
    if mutation_handler is None and mutation_engine is not None:
        mutation_handler = mutation_engine.execute_mutation_cycle
    return AutoresearchCycle(
        state=state,
        tiers=["tier-1", "tier-2"],
        operations=FakeCycleOperations(
            benchmark,
            events,
            verifier_adapter=verifier_adapter,
            mutation_handler=mutation_handler,
        ),
    )


def test_cycle_success_escalates_and_preserves_side_effect_order() -> None:
    state = _state()
    events: list[str] = []
    cycle = _cycle(
        state,
        {"summary": {"success_rate": "4/4"}},
        events=events,
    )

    result = cycle.run()

    assert result.status == "success"
    assert result.pass_rate == 100.0
    assert result.signal_receipt == "signal-1"
    assert result.state["current_tier"] == "tier-2"
    assert events == ["telemetry", "signal", "save", "parity"]


def test_cycle_rejection_runs_mutation_and_persists_state() -> None:
    state = _state()
    events: list[str] = []
    mutation = Mock(return_value=SimpleNamespace(decision="REJECT"))
    cycle = _cycle(
        state,
        {"summary": {"success_rate": "1/4"}},
        events=events,
        verifier_adapter=lambda _benchmark: _verification(0.25),
        mutation_adapter=mutation,
    )

    result = cycle.run()

    assert result.mutation_decision == "REJECT"
    assert result.circuit_breaker_open is False
    assert result.state["mutation_count"] == 1
    mutation.assert_called_once()
    assert events == ["telemetry", "signal", "mutation", "save", "parity"]


def test_cycle_mutation_noop_preserves_existing_result_shape() -> None:
    state = _state()
    events: list[str] = []
    mutation_engine = Mock()
    mutation_engine.execute_mutation_cycle.return_value = None
    cycle = _cycle(
        state,
        {"summary": {"success_rate": "1/4"}},
        events=events,
        verifier_adapter=lambda _benchmark: _verification(0.25),
        mutation_engine=mutation_engine,
    )

    result = cycle.run()

    assert result.mutation_decision is None
    assert result.state["mutation_count"] == 1
    mutation_engine.execute_mutation_cycle.assert_called_once()


def test_cycle_stable_range_resets_mutation_count() -> None:
    state = _state(mutation_count=2)
    events: list[str] = []
    cycle = _cycle(
        state,
        {"summary": {"success_rate": "2/4"}},
        events=events,
    )

    result = cycle.run()

    assert result.pass_rate == 50.0
    assert result.state["current_tier"] == "tier-1"
    assert result.state["mutation_count"] == 0
    assert events == ["telemetry", "signal", "save", "parity"]


def test_cycle_circuit_breaker_drops_tier_and_skips_mutation() -> None:
    state = _state(mutation_count=2)
    state["current_tier"] = "tier-2"
    events: list[str] = []
    cycle = _cycle(
        state,
        {"summary": {"success_rate": "1/4"}},
        events=events,
    )

    result = cycle.run()

    assert result.circuit_breaker_open is True
    assert result.state["current_tier"] == "tier-1"
    assert result.state["mutation_count"] == 0
    assert events == ["telemetry", "signal", "save", "parity"]


def test_cycle_pin_override_maintains_pinned_tier(monkeypatch) -> None:
    monkeypatch.setenv("MIGHTY_MOUSE_PIN_TIER", "tier-2")
    state = _state()
    events: list[str] = []
    cycle = _cycle(
        state,
        {"summary": {"success_rate": "1/4"}},
        events=events,
    )

    result = cycle.run()

    assert result.circuit_breaker_open is False
    assert result.state["current_tier"] == "tier-2"
    assert result.state["mutation_count"] == 0
    assert events == ["telemetry", "signal", "save", "parity"]


def test_cycle_benchmark_failure_requests_retry_without_side_effects() -> None:
    state = _state()
    events: list[str] = []
    cycle = _cycle(state, None, events=events)

    result = cycle.run()

    assert result == CycleResult(
        status="retry_needed", tier="tier-1", state=state
    )
    assert events == []


def test_cycle_evaluator_failure_preserves_exception_boundary() -> None:
    state = _state()
    events: list[str] = []

    def fail_verification(_benchmark: dict) -> VerificationResult:
        raise RuntimeError("evaluator unavailable")

    cycle = _cycle(
        state,
        {"summary": {"success_rate": "1/4"}},
        events=events,
        verifier_adapter=fail_verification,
    )

    with pytest.raises(RuntimeError, match="evaluator unavailable"):
        cycle.run()

    assert state["total_iterations"] == 1
    assert events == []


def test_loop_cycle_state_write_and_restore(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    telemetry_path = tmp_path / "telemetry.json"
    results_path = tmp_path / "results.json"
    state_dir = tmp_path / "v2-state"
    loop = AutoresearchLoop(
        state_path=str(state_path),
        telemetry_path=str(telemetry_path),
        benchmark_results_path=str(results_path),
        mutation_engine=Mock(),
        state_dir=str(state_dir),
        benchmark_adapter=lambda _tier: {
            "summary": {"success_rate": "4/4"}
        },
        verifier_adapter=lambda _benchmark: _verification(1.0),
    )
    loop._run_parity_report = Mock()

    result = loop.run_single_cycle()

    restored = AutoresearchLoop(
        state_path=str(state_path),
        telemetry_path=str(telemetry_path),
        benchmark_results_path=str(results_path),
        mutation_engine=Mock(),
        state_dir=str(state_dir),
        benchmark_adapter=lambda _tier: None,
    )
    assert result.state["total_iterations"] == 1
    assert result.state["current_tier"] == loop.tiers[1]
    assert restored.state == result.state


def test_run_forever_delegates_repeated_cycles(
    monkeypatch, tmp_path: Path
) -> None:
    loop = AutoresearchLoop(
        state_path=str(tmp_path / "state.json"),
        telemetry_path=str(tmp_path / "telemetry.json"),
        benchmark_results_path=str(tmp_path / "results.json"),
        mutation_engine=Mock(),
        state_dir=str(tmp_path / "v2-state"),
    )
    run_cycle = Mock(
        side_effect=[
            CycleResult(status="success", tier="tier-1"),
            CycleResult(status="success", tier="tier-1"),
        ]
    )
    loop.run_single_cycle = run_cycle
    monkeypatch.setattr(
        perpetual_loop_module.signal, "signal", lambda *_args: None
    )

    def stop_after_two(_sleep_seconds: int) -> None:
        if run_cycle.call_count == 2:
            raise KeyboardInterrupt

    monkeypatch.setattr(perpetual_loop_module.time, "sleep", stop_after_two)

    with pytest.raises(KeyboardInterrupt):
        loop.run_forever(sleep_sec=0)

    assert run_cycle.call_count == 2


def test_loop_single_cycle_delegates_to_bounded_cycle(tmp_path: Path) -> None:
    loop = AutoresearchLoop(
        state_path=str(tmp_path / "state.json"),
        telemetry_path=str(tmp_path / "telemetry.json"),
        benchmark_results_path=str(tmp_path / "results.json"),
        mutation_engine=Mock(),
        state_dir=str(tmp_path / "v2-state"),
    )
    expected = LoopCycleResult(status="retry_needed", tier="tier-1")
    bounded_cycle = Mock()
    bounded_cycle.run.return_value = expected
    loop.build_cycle = Mock(return_value=bounded_cycle)

    result = loop.run_single_cycle()

    assert result is expected
    loop.build_cycle.assert_called_once_with()
    bounded_cycle.run.assert_called_once_with()
    assert LoopCycleResult is CycleResult
