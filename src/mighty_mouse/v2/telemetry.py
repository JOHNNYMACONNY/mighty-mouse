"""Telemetry aggregation and pass rate calculation for Mighty Mouse v2."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from mighty_mouse.v2.foundation import ImmutableStateStore, Scope, Signal
from mighty_mouse.v2.signals import SignalLifecycle

_SIGNAL_OUTCOME_PASSED = "passed"


class TelemetryAggregator:
    """Aggregates execution signals from ImmutableStateStore and SignalLifecycle to compute windowed metrics."""

    def __init__(
        self,
        store: ImmutableStateStore,
        signal_lifecycle: Optional[SignalLifecycle] = None,
        default_window_size: int = 20,
    ) -> None:
        self.store = store
        self.signal_lifecycle = signal_lifecycle
        self.default_window_size = default_window_size

    def get_signals_for_scope(self, scope: Scope) -> List[Signal]:
        """Fetch all recorded signals matching the exact given Scope."""
        matched: List[Signal] = []
        for record in self.store.records():
            if isinstance(record.value, Signal) and record.value.scope == scope:
                matched.append(record.value)
        return matched

    def _get_window_signals(
        self,
        scope: Scope,
        window_size: Optional[int] = None,
    ) -> Tuple[List[Signal], int]:
        """Extract matching signals within the effective sliding window."""
        effective_window_size = window_size if window_size is not None else self.default_window_size
        signals = self.get_signals_for_scope(scope)
        if not signals or effective_window_size <= 0:
            return [], effective_window_size
        return signals[-effective_window_size:], effective_window_size

    def _count_passed_signals(self, window_signals: List[Signal]) -> int:
        """Count the total number of signals with a passed outcome."""
        return sum(1 for s in window_signals if s.outcome == _SIGNAL_OUTCOME_PASSED)


    def compute_pass_rate(
        self,
        scope: Scope,
        window_size: Optional[int] = None,
    ) -> Optional[float]:
        """Compute the pass rate across the sliding window of recent signals for a given Scope.
        
        Returns None if no signals exist for the scope or window_size <= 0.
        """
        window_signals, _ = self._get_window_signals(scope, window_size)
        if not window_signals:
            return None

        passed_count = self._count_passed_signals(window_signals)
        return passed_count / len(window_signals)

    def get_telemetry_summary(
        self,
        scope: Scope,
        window_size: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Return structured summary metrics for a given Scope."""
        window_signals, effective_window_size = self._get_window_signals(scope, window_size)
        if not window_signals:
            return {
                "scope": scope,
                "pass_rate": None,
                "total_signals": 0,
                "passed_signals": 0,
                "failed_signals": 0,
                "avg_duration_ms": 0.0,
                "window_size": effective_window_size,
            }

        passed_count = self._count_passed_signals(window_signals)
        failed_count = len(window_signals) - passed_count
        total_duration = sum(s.duration_ms for s in window_signals)

        return {
            "scope": scope,
            "pass_rate": passed_count / len(window_signals),
            "total_signals": len(window_signals),
            "passed_signals": passed_count,
            "failed_signals": failed_count,
            "avg_duration_ms": total_duration / len(window_signals),
            "window_size": effective_window_size,
        }
