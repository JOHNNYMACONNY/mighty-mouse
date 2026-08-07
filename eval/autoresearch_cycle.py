"""Bounded one-cycle execution for the Autoresearch Harness."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import os
from typing import Any, Callable, Dict, List, Optional

try:
    from .tier_utils import parse_pass_rate
except ImportError:
    from tier_utils import parse_pass_rate

from mighty_mouse.v2.seams import PolicyMutationSurface, VerificationResult


@dataclass(frozen=True)
class CycleResult:
    """Typed result for one Harness cycle, with legacy mapping access."""

    status: str
    tier: str
    pass_rate: float | None = None
    benchmark: Dict[str, Any] | None = None
    verification: VerificationResult | None = None
    signal_receipt: str | None = None
    mutation_decision: str | None = None
    circuit_breaker_open: bool = False
    state: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "tier": self.tier,
            "pass_rate": self.pass_rate,
            "benchmark": self.benchmark,
            "verification": None
            if self.verification is None
            else {
                "passed": self.verification.passed,
                "score": self.verification.score,
                "details": dict(self.verification.details),
                "verdict_category": self.verification.verdict_category,
            },
            "signal_receipt": self.signal_receipt,
            "mutation_decision": self.mutation_decision,
            "circuit_breaker_open": self.circuit_breaker_open,
            "state": dict(self.state),
        }

    def __getitem__(self, key: str) -> Any:
        return self.to_dict()[key]


class AutoresearchCycle:
    """Execute one bounded benchmark, verification, mutation, and save cycle.
    """

    def __init__(
        self,
        *,
        state: Dict[str, Any],
        tiers: List[str],
        run_benchmark: Callable[[str], Optional[Dict[str, Any]]],
        update_telemetry: Callable[[str, Dict[str, Any], str], None],
        record_signal: Callable[..., Any],
        save_state: Callable[[], None],
        run_parity_report: Callable[[], None],
        config_hash_provider: Callable[[], str],
        replay_tiers_provider: Callable[[str], List[str]],
        mutation_engine: Any,
        verifier_adapter: Optional[
            Callable[[Dict[str, Any]], VerificationResult]
        ],
        mutation_adapter: Optional[Callable[..., Any]],
        mutation_surface: PolicyMutationSurface,
    ) -> None:
        self.state = state
        self.tiers = tiers
        self.run_benchmark = run_benchmark
        self.update_telemetry = update_telemetry
        self.record_signal = record_signal
        self.save_state = save_state
        self.run_parity_report = run_parity_report
        self.config_hash_provider = config_hash_provider
        self.replay_tiers_provider = replay_tiers_provider
        self.mutation_engine = mutation_engine
        self.verifier_adapter = verifier_adapter
        self.mutation_adapter = mutation_adapter
        self.mutation_surface = mutation_surface

    def run(self) -> CycleResult:
        """Run exactly one existing AutoresearchLoop cycle."""
        current_tier = self.state["current_tier"]
        config_hash = self.config_hash_provider()

        print(f"\n--- Cycle Start: {datetime.now().isoformat()} ---")
        print(f"[*] Iteration: {self.state['total_iterations'] + 1}")
        print(f"[*] Current Tier: {current_tier}")
        print(f"[*] Config Hash: {config_hash}")
        print(f"[*] Mutation Count: {self.state['mutation_count']}")

        bench_data = self.run_benchmark(current_tier)
        if not bench_data:
            print("[!] No benchmark data received.")
            return CycleResult(
                status="retry_needed",
                tier=current_tier,
                state=dict(self.state),
            )

        self.state["total_iterations"] += 1
        summary = bench_data.get("summary", {})
        success_rate_str = summary.get("success_rate", "0/0")
        if self.verifier_adapter is not None:
            verification = self.verifier_adapter(bench_data)
            pass_rate = verification.score * 100.0
        else:
            pass_rate = parse_pass_rate(summary) * 100.0
            verification = VerificationResult(
                passed=pass_rate >= 100.0,
                score=pass_rate / 100.0,
                details={"verifier_category": "LOGIC"},
                verdict_category="PASS" if pass_rate >= 100.0 else "FAIL",
            )

        print(f"[*] Results: {success_rate_str} ({pass_rate:.1f}%)")
        self.update_telemetry(current_tier, summary, config_hash)

        cycle_scope = self._cycle_scope()
        cycle_outcome = "passed" if pass_rate >= 50.0 else "failed"
        signal_receipt = self.record_signal(
            scope=cycle_scope,
            outcome=cycle_outcome,
            signal_counter=max(1, self.state["total_iterations"]),
        )

        pinned_tier = os.environ.get("MIGHTY_MOUSE_PIN_TIER")
        mutation_decision = None
        circuit_breaker_open = False
        if pinned_tier and pinned_tier in self.tiers:
            self.state["current_tier"] = pinned_tier
            print(
                f"[!] Tier Pinned: maintaining {pinned_tier} "
                "per user Pin override."
            )
            self.state["mutation_count"] = 0
        elif pass_rate >= 90:
            print("[+] Escalation criteria met (>=90%).")
            self.state["mutation_count"] = 0
            current_idx = (
                self.tiers.index(current_tier)
                if current_tier in self.tiers
                else 0
            )
            if current_idx < len(self.tiers) - 1:
                self.state["current_tier"] = self.tiers[current_idx + 1]
                print(f"[+] Escalating to {self.state['current_tier']}")
            else:
                print("[*] Already at highest tier. Maintaining.")
        elif pass_rate < 50:
            print("[-] Mutation criteria met (<50%).")
            self.state["mutation_count"] += 1

            if self.state["mutation_count"] >= 3:
                circuit_breaker_open = True
                print(
                    "[!] Circuit breaker triggered: 3 consecutive failing "
                    "mutation cycles."
                )
                current_idx = (
                    self.tiers.index(current_tier)
                    if current_tier in self.tiers
                    else 0
                )
                if current_idx > 0:
                    self.state["current_tier"] = self.tiers[current_idx - 1]
                    print(f"[!] Dropping back to {self.state['current_tier']}")
                else:
                    print("[!] Already at lowest tier. Staying here.")
                self.state["mutation_count"] = 0
            else:
                print(
                    f"[*] Triggering in-process mutation cycle "
                    f"(Attempt {self.state['mutation_count']}/3)..."
                )
                replay_tiers = self.replay_tiers_provider(current_tier)
                if self.mutation_adapter is not None:
                    record = self.mutation_adapter(
                        verification, current_tier, replay_tiers
                    )
                else:
                    record = self.mutation_engine.execute_mutation_cycle(
                        current_tier=current_tier,
                        replay_tiers=replay_tiers,
                        mutation_surface=self.mutation_surface,
                        verification_result=verification,
                    )
                mutation_decision = getattr(record, "decision", None)
                record_decision = getattr(
                    record, "decision", record if record else "None"
                )
                print(
                    "[*] Mutation cycle finished. Record decision: "
                    f"{record_decision}"
                )
        else:
            print(
                "[*] Performance in stable range (50% - 90%). "
                "Maintaining current tier."
            )
            self.state["mutation_count"] = 0

        self.save_state()
        self.run_parity_report()

        return CycleResult(
            status="success",
            tier=current_tier,
            pass_rate=pass_rate,
            benchmark=bench_data,
            verification=verification,
            signal_receipt=signal_receipt,
            mutation_decision=mutation_decision,
            circuit_breaker_open=circuit_breaker_open,
            state=dict(self.state),
        )

    @staticmethod
    def _cycle_scope():
        from mighty_mouse.v2.foundation import Mode, Scope, TaskCategory

        return Scope(
            mode=Mode.AGENTIC,
            repository="JOHNNYMACONNY/mighty-mouse",
            task_category=TaskCategory.MAINTENANCE,
            model_class="local-small",
        )
