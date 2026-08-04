from pathlib import Path

from mighty_mouse.v2.engine import PolicyEngine
from mighty_mouse.v2.foundation import Mode, Scope, Signal, TaskCategory
from mighty_mouse.v2.signals import SignalLifecycle


def _scope() -> Scope:
    return Scope(Mode.AGENTIC, "JOHNNYMACONNY/mighty-mouse", TaskCategory.MAINTENANCE, "local-small")


def _signal(scope: Scope, number: int, outcome: str) -> Signal:
    return Signal(
        f"signal-{number:03d}", scope, "sha256:" + "a" * 64, "codex-local", outcome, 100 + number, 0, "tests", outcome,
    )


def test_host_harness_and_policy_engine_share_signal_aggregates(tmp_path: Path) -> None:
    scope = _scope()
    lifecycle = SignalLifecycle(tmp_path)
    lifecycle.collect(_signal(scope, 1, "passed"))

    engine = PolicyEngine(tmp_path)
    lifecycle_from_harness = SignalLifecycle(tmp_path)
    lifecycle_from_harness.collect(_signal(scope, 2, "failed"))
    receipt = engine.record_signal(_signal(scope, 3, "passed"))

    summary = lifecycle.get_signal_summary(scope)
    assert receipt is not None
    assert receipt.record_hash == str(receipt)
    assert summary["total_signals"] == 3
    assert summary["passed_signals"] == 2
    assert summary["pass_rate"] == 2 / 3


def test_signal_summary_preserves_filters_pause_and_empty_window(tmp_path: Path) -> None:
    scope = _scope()
    lifecycle = SignalLifecycle(tmp_path)
    lifecycle.collect(_signal(scope, 1, "passed"))
    lifecycle.pause()
    assert lifecycle.collect(_signal(scope, 2, "failed")) is None
    assert lifecycle.compute_pass_rate(scope, window_size=0) is None
    assert lifecycle.get_signal_summary(scope, model_digest="sha256:" + "b" * 64)["total_signals"] == 0
    lifecycle.resume()
    lifecycle.collect(_signal(scope, 3, "failed"))
    assert lifecycle.compute_pass_rate(scope) == 0.5
