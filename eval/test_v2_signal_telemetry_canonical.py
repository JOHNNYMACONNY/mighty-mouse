from datetime import datetime, timezone
import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from mighty_mouse.commands.signals_cmd import run_signals
from mighty_mouse.v2.engine import PolicyEngine
from mighty_mouse.v2.foundation import (
    ExecutionProfile,
    ImmutableStateStore,
    Mode,
    ModelIdentity,
    Scope,
    Signal,
    TaskCategory,
)
from mighty_mouse.v2.signals import SignalLifecycle
from mighty_mouse.v2.telemetry import SignalAggregator, SignalTelemetry
from perpetual_loop import AutoresearchLoop


def _scope() -> Scope:
    return Scope(
        Mode.AGENTIC,
        "JOHNNYMACONNY/mighty-mouse",
        TaskCategory.MAINTENANCE,
        "local-small",
    )


def _signal(scope: Scope, signal_id: str = "signal-001") -> Signal:
    return Signal(
        signal_id=signal_id,
        scope=scope,
        model_digest="sha256:" + "a" * 64,
        execution_profile_id="codex-local",
        outcome="passed",
        duration_ms=120,
        retry_count=1,
        verifier_category="tests",
        verifier_result="passed",
        environment_metadata=(("os", "macos"),),
        rating=5,
    )


def _record_kwargs(scope: Scope, signal_id: str = "signal-001") -> dict:
    return {
        "signal_id": signal_id,
        "scope": scope,
        "model_digest": "sha256:" + "a" * 64,
        "execution_profile_id": "codex-local",
        "outcome": "passed",
        "duration_ms": 120,
        "retry_count": 1,
        "verifier_category": "tests",
        "verifier_result": "passed",
        "environment_metadata": (("os", "macos"),),
        "rating": 5,
    }


def test_canonical_record_matches_direct_signal_receipt_bytes(
    tmp_path: Path,
) -> None:
    scope = _scope()
    collected_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    direct_dir = tmp_path / "direct"
    canonical_dir = tmp_path / "canonical"

    direct_lifecycle = SignalLifecycle(direct_dir)
    direct_receipt = direct_lifecycle.collect(
        _signal(scope), now=collected_at
    )
    canonical_lifecycle = SignalLifecycle(canonical_dir)
    canonical_receipt = SignalTelemetry(canonical_lifecycle).record(
        **_record_kwargs(scope), now=collected_at
    )

    assert canonical_receipt == direct_receipt
    direct_file = next(direct_lifecycle.receipt_dir.glob("*.json"))
    canonical_file = next(canonical_lifecycle.receipt_dir.glob("*.json"))
    assert canonical_file.read_bytes() == direct_file.read_bytes()


def test_canonical_telemetry_owns_lifecycle_aggregation(
    tmp_path: Path,
) -> None:
    scope = _scope()
    lifecycle = SignalLifecycle(tmp_path)
    telemetry = SignalTelemetry(lifecycle)
    telemetry.record(**_record_kwargs(scope, "signal-001"))
    telemetry.record(
        **(_record_kwargs(scope, "signal-002") | {
            "outcome": "failed",
            "verifier_result": "failed",
        })
    )

    compatibility = SignalAggregator(
        ImmutableStateStore(tmp_path), signal_lifecycle=lifecycle
    )

    assert telemetry.compute_pass_rate(scope) == 0.5
    compatibility_summary = compatibility.get_signal_summary(scope)
    canonical_summary = telemetry.get_signal_summary(scope)
    assert compatibility_summary == canonical_summary
    assert compatibility.get_signals_for_scope(scope) == []


def test_signal_aggregator_lifecycle_path_delegates_to_canonical(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    delegate = Mock()
    monkeypatch.setattr(
        "mighty_mouse.v2.telemetry.SignalTelemetry",
        lambda lifecycle, default_window_size: delegate,
    )
    aggregator = SignalAggregator(
        ImmutableStateStore(tmp_path),
        signal_lifecycle=SignalLifecycle(tmp_path),
    )

    aggregator.compute_pass_rate(_scope(), window_size=4)

    delegate.compute_pass_rate.assert_called_once_with(_scope(), 4)


def test_canonical_record_preserves_signal_validation(tmp_path: Path) -> None:
    telemetry = SignalTelemetry(SignalLifecycle(tmp_path))

    with pytest.raises(ValueError, match="outcome"):
        invalid = _record_kwargs(_scope()) | {"outcome": "prompt text"}
        telemetry.record(**invalid)


def test_canonical_signal_history_reaches_status_projection(
    tmp_path: Path,
) -> None:
    scope = _scope()
    identity = ModelIdentity("sha256:" + "a" * 64)
    profile = ExecutionProfile("codex-local", frozenset({"test"}))
    SignalTelemetry(SignalLifecycle(tmp_path)).record(**_record_kwargs(scope))

    status = PolicyEngine(tmp_path).get_status(scope, identity, profile)

    assert status["signals"]["receipt_count"] == 1


def test_policy_engine_routes_signal_emission_through_canonical_seam(
    tmp_path: Path,
) -> None:
    engine = PolicyEngine(tmp_path)
    collector = Mock(return_value="receipt")
    engine._signal_telemetry.collect = collector
    signal = _signal(_scope())

    assert engine.record_signal(signal) == "receipt"
    collector.assert_called_once_with(signal)


def test_autoresearch_loop_routes_signal_construction_through_canonical_seam(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    recorder = Mock(return_value="receipt")
    monkeypatch.setattr("perpetual_loop.SignalTelemetry.record", recorder)
    loop = AutoresearchLoop(
        state_path=str(tmp_path / "state.json"),
        telemetry_path=str(tmp_path / "telemetry.json"),
        benchmark_results_path=str(tmp_path / "results.json"),
        mutation_engine=Mock(),
        state_dir=str(tmp_path / "v2-state"),
    )

    result = loop.record_signal(
        scope=_scope(), outcome="passed", signal_counter=7
    )

    assert result == "receipt"
    assert loop.telemetry_aggregator is loop.signal_telemetry
    assert isinstance(loop.telemetry_aggregator, SignalTelemetry)
    assert not (tmp_path / "telemetry.json").exists()
    assert recorder.call_args.kwargs["signal_id"] == "signal-007"
    assert recorder.call_args.kwargs["scope"] == _scope()


def test_cli_routes_signal_construction_through_canonical_seam(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    recorder = Mock(return_value="receipt")
    monkeypatch.setattr(
        "mighty_mouse.commands.signals_cmd.SignalTelemetry.record", recorder
    )

    run_signals(
        action="collect",
        state_dir=str(tmp_path),
        signal_id="signal-001",
        repository="JOHNNYMACONNY/mighty-mouse",
        mode="coding",
        task_category="feature",
        model_class="local-small",
        model_digest="sha256:" + "a" * 64,
        execution_profile="codex-local",
        outcome="passed",
        duration_ms=10,
        retry_count=0,
        verifier_category="tests",
        verifier_result="passed",
        rating=None,
        json_output=True,
    )

    assert json.loads(capsys.readouterr().out)["collected"] is True
    recorder.assert_called_once()
