from pathlib import Path
from datetime import datetime
from unittest.mock import Mock

import pytest

from eval.autoresearch_harness import SingleInstanceLock as LegacyLock
from eval.autoresearch_cycle import MutationRequest
from eval.mutation_engine import MutationLogRecord
from eval.perpetual_loop import (
    AutoresearchLoop,
    CycleResult,
)
from eval.runner_lock import SingleInstanceLock, SingleInstanceLockError
from mighty_mouse.v2.seams import VerificationResult


def test_loop_cycle_uses_injected_benchmark_verifier_and_mutation_adapters(tmp_path: Path) -> None:
    mutations = []

    def mutate(request: MutationRequest):
        assert isinstance(request.verification, VerificationResult)
        mutations.append((request.current_tier, request.replay_tiers))
        return MutationLogRecord(
            timestamp=datetime.now().isoformat(),
            failure_category="LOGIC",
            segment_changed="none",
            hypothesis="test",
            before=None,
            after=None,
            replay_tiers_tested=list(request.replay_tiers),
            decision="REJECT",
        )

    loop = AutoresearchLoop(
        state_path=str(tmp_path / "state.json"),
        telemetry_path=str(tmp_path / "telemetry.json"),
        benchmark_results_path=str(tmp_path / "results.json"),
        mutation_engine=Mock(),
        state_dir=str(tmp_path / "v2-state"),
        benchmark_adapter=lambda tier: {"summary": {"success_rate": "1/4"}},
        verifier_adapter=lambda result: VerificationResult(
            passed=False,
            score=0.25,
            details={"verifier_category": "LOGIC"},
            verdict_category="FAIL",
        ),
        mutation_adapter=mutate,
    )
    result = loop.run_single_cycle()
    assert isinstance(result, CycleResult)
    assert result.pass_rate == 25.0
    assert result.signal_receipt is not None
    assert mutations
    assert result.mutation_decision == "REJECT"


def test_loop_operations_preserve_fallback_verification(
    tmp_path: Path,
) -> None:
    loop = AutoresearchLoop(
        state_path=str(tmp_path / "state.json"),
        telemetry_path=str(tmp_path / "telemetry.json"),
        benchmark_results_path=str(tmp_path / "results.json"),
        mutation_engine=Mock(),
        state_dir=str(tmp_path / "v2-state"),
        benchmark_adapter=lambda _tier: {"summary": {"success_rate": "1/4"}},
    )
    loop.mutation_engine.execute_mutation_cycle.return_value = None
    loop._run_parity_report = lambda: None

    cycle = loop.build_cycle()

    assert cycle.operations is loop
    result = cycle.run()

    assert result.pass_rate == 25.0
    assert result.verification is not None
    assert result.verification.verdict_category == "FAIL"
    loop.mutation_engine.execute_mutation_cycle.assert_called_once()
    request = loop.mutation_engine.execute_mutation_cycle.call_args.kwargs
    assert request["current_tier"] == loop.tiers[0]
    assert request["replay_tiers"] == []
    assert isinstance(request["verification_result"], VerificationResult)


def test_harness_adapters_share_one_lock_implementation(tmp_path: Path) -> None:
    assert LegacyLock is SingleInstanceLock
    lock_path = tmp_path / "runner.lock"
    with SingleInstanceLock(lock_path):
        with pytest.raises(SingleInstanceLockError):
            with SingleInstanceLock(lock_path):
                pass
