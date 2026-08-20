"""Signal aggregate telemetry calculation for Mighty Mouse v2.

Maps structured Signal observations from ImmutableStateStore and SignalLifecycle
to compute windowed pass rates and aggregate metrics.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from enum import Enum
import time

from mighty_mouse.v2.foundation import ImmutableStateStore, Scope, Signal
from mighty_mouse.v2.signals import SignalLifecycle


__all__ = ("SignalTelemetry", "SignalAggregator", "TelemetryAggregator")


class SignalOutcome(str, Enum):
    """Canonical Signal execution outcomes."""
    PASSED = "passed"
    FAILED = "failed"


class SignalTelemetry:
    """Canonical lifecycle-backed Signal construction, emission, and
    aggregation.
    """

    def __init__(
        self,
        signal_lifecycle: SignalLifecycle,
        default_window_size: int = 20,
    ) -> None:
        self.signal_lifecycle = signal_lifecycle
        self.default_window_size = default_window_size

    def record(
        self,
        *,
        signal_id: str,
        scope: Scope,
        model_digest: str,
        execution_profile_id: str,
        outcome: str,
        duration_ms: int,
        retry_count: int,
        verifier_category: str,
        verifier_result: str = "not_run",
        environment_metadata: tuple[tuple[str, str], ...] = (),
        rating: int | None = None,
        now: datetime | None = None,
    ) -> str | None:
        """Construct and persist one validated, privacy-safe Signal."""
        signal = Signal(
            signal_id=signal_id,
            scope=scope,
            model_digest=model_digest,
            execution_profile_id=execution_profile_id,
            outcome=outcome,
            duration_ms=duration_ms,
            retry_count=retry_count,
            verifier_category=verifier_category,
            verifier_result=verifier_result,
            environment_metadata=environment_metadata,
            rating=rating,
        )
        return self.collect(signal, now=now)

    def collect(
        self, signal: Signal, *, now: datetime | None = None
    ) -> str | None:
        """Emit an already constructed Signal through canonical persistence."""
        return self.signal_lifecycle.collect(signal, now=now)

    def get_signals_for_scope(self, scope: Scope) -> List[Signal]:
        """Keep raw Signal fields behind SignalLifecycle's privacy boundary."""
        return []

    def get_signals_for_retention_window(
        self,
        scope: Scope,
        max_age_seconds: int = 30 * 86400,
    ) -> List[Signal]:
        """Keep detailed Signal lookup unavailable on canonical lifecycle
        path.
        """
        return self.get_signals_for_scope(scope)

    def signal_count_for_scope(
        self,
        scope: Scope,
        window_size: Optional[int] = None,
    ) -> int:
        """Return lifecycle-backed count for exact Scope and optional
        window.
        """
        return int(
            self.signal_lifecycle.get_signal_summary(
                scope, window_size=window_size
            )["total_signals"]
        )

    def _get_window_signals(
        self,
        scope: Scope,
        window_size: Optional[int] = None,
    ) -> Tuple[List[Signal], int]:
        """Preserve legacy private helper behavior on lifecycle-backed
        path.
        """
        effective_window_size = (
            window_size
            if window_size is not None
            else self.default_window_size
        )
        signals = self.get_signals_for_scope(scope)
        if not signals or effective_window_size <= 0:
            return [], effective_window_size
        return signals[-effective_window_size:], effective_window_size

    def _count_passed_signals(self, window_signals: List[Signal]) -> int:
        """Count passed outcomes in a detailed Signal window."""
        return sum(
            1
            for signal in window_signals
            if signal.outcome in (
                SignalOutcome.PASSED,
                SignalOutcome.PASSED.value,
            )
        )

    def compute_pass_rate(
        self,
        scope: Scope,
        window_size: Optional[int] = None,
    ) -> Optional[float]:
        """Return lifecycle-backed pass rate for exact Scope."""
        return self.signal_lifecycle.compute_pass_rate(
            scope, window_size=window_size
        )

    def get_signal_summary(
        self,
        scope: Scope,
        window_size: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Return lifecycle-backed privacy-safe aggregate metrics."""
        return self.signal_lifecycle.get_signal_summary(
            scope, window_size=window_size
        )

    def get_profile_telemetry(
        self,
        *,
        execution_profile_id: Optional[str] = None,
        model_digest: Optional[str] = None,
        window_size: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Return cross-host profile-partitioned aggregate telemetry."""
        return self.signal_lifecycle.profile_summary(
            execution_profile_id=execution_profile_id,
            model_digest=model_digest,
            window_size=window_size,
        )

    get_telemetry_summary = get_signal_summary
    profile_summary = get_profile_telemetry


class _LegacyStoreSignalTelemetry:
    """Migration-only adapter for raw ImmutableStateStore Signals."""

    def __init__(
        self,
        store: ImmutableStateStore,
        default_window_size: int = 20,
    ) -> None:
        self.store = store
        self.default_window_size = default_window_size

    def get_signals_for_scope(self, scope: Scope) -> List[Signal]:
        """Fetch all recorded signals matching the exact given Scope."""
        matched: List[Signal] = []
        for record in self.store.records():
            if isinstance(record.value, Signal) and record.value.scope == scope:
                matched.append(record.value)
        return matched

    def get_signals_for_retention_window(
        self,
        scope: Scope,
        max_age_seconds: int = 30 * 86400,
    ) -> List[Signal]:
        """Filter signals for a scope within a 30-day retention window."""
        now = time.time()
        signals = self.get_signals_for_scope(scope)
        return [s for s in signals if (now - getattr(s, 'timestamp', 0.0)) <= max_age_seconds]

    def signal_count_for_scope(self, scope: Scope, window_size: Optional[int] = None) -> int:
        """Return the count of recorded signals matching the given Scope within optional sliding window."""
        if window_size is not None:
            window_signals, _ = self._get_window_signals(scope, window_size)
            return len(window_signals)
        return len(self.get_signals_for_scope(scope))

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
        return sum(1 for s in window_signals if s.outcome in (SignalOutcome.PASSED, SignalOutcome.PASSED.value))

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

    def get_signal_summary(
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

    get_telemetry_summary = get_signal_summary


class SignalAggregator:
    """Public compatibility facade for canonical SignalTelemetry.

    Lifecycle-backed construction routes to SignalTelemetry. Store-only
    construction retains legacy raw-store semantics for compatibility callers.
    """

    def __init__(
        self,
        store: ImmutableStateStore,
        signal_lifecycle: Optional[SignalLifecycle] = None,
        default_window_size: int = 20,
    ) -> None:
        self.store = store
        self.signal_lifecycle = signal_lifecycle
        self.default_window_size = default_window_size
        self._delegate = (
            SignalTelemetry(signal_lifecycle, default_window_size)
            if signal_lifecycle is not None
            else _LegacyStoreSignalTelemetry(store, default_window_size)
        )

    def get_signals_for_scope(self, scope: Scope) -> List[Signal]:
        return self._delegate.get_signals_for_scope(scope)

    def get_signals_for_retention_window(
        self,
        scope: Scope,
        max_age_seconds: int = 30 * 86400,
    ) -> List[Signal]:
        return self._delegate.get_signals_for_retention_window(
            scope, max_age_seconds
        )

    def signal_count_for_scope(
        self,
        scope: Scope,
        window_size: Optional[int] = None,
    ) -> int:
        return self._delegate.signal_count_for_scope(scope, window_size)

    def _get_window_signals(
        self,
        scope: Scope,
        window_size: Optional[int] = None,
    ) -> Tuple[List[Signal], int]:
        return self._delegate._get_window_signals(scope, window_size)

    def _count_passed_signals(self, window_signals: List[Signal]) -> int:
        return self._delegate._count_passed_signals(window_signals)

    def compute_pass_rate(
        self,
        scope: Scope,
        window_size: Optional[int] = None,
    ) -> Optional[float]:
        return self._delegate.compute_pass_rate(scope, window_size)

    def get_signal_summary(
        self,
        scope: Scope,
        window_size: Optional[int] = None,
    ) -> Dict[str, Any]:
        return self._delegate.get_signal_summary(scope, window_size)

    get_telemetry_summary = get_signal_summary


# Public compatibility alias retained for existing TelemetryAggregator imports.
TelemetryAggregator = SignalAggregator
