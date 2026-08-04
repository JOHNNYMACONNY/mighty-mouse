import json
import logging
import os
import subprocess
import time
import signal
import sys
import hashlib
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field
from typing import Callable, Dict, Any, Optional, List

logger = logging.getLogger(__name__)

# Configuration
CONFIG_PATH = "eval/evaluation_config.json"
STATE_PATH = "logs/perpetual_state.json"
TELEMETRY_PATH = "logs/metric_telemetry.json"
BENCHMARK_RESULTS_PATH = "eval/results/benchmark_results.json"
AGENT_CONFIG_PATH = "configs/mighty_mouse_v2_lean.yaml"

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_EVAL_DIR = os.path.dirname(os.path.abspath(__file__))
if _EVAL_DIR not in sys.path:
    sys.path.append(_EVAL_DIR)
if _REPO_ROOT not in sys.path:
    sys.path.append(_REPO_ROOT)


from tier_utils import load_tier_sequence, parse_pass_rate
from mutation_engine import CATEGORY_TO_SEGMENT, MutationEngine, MutationLogRecord, get_replay_tiers
from mighty_mouse.v2.foundation import (
    ImmutableStateStore,
    Mode,
    Scope,
    Signal,
    TaskCategory,
)
from mighty_mouse.v2.signals import SignalLifecycle
from mighty_mouse.v2.seams import PolicyMutationSurface, VerificationResult
from mighty_mouse.v2.telemetry import TelemetryAggregator
try:
    from .runner_lock import LOCK_FILE_PATH, SingleInstanceLock, SingleInstanceLockError
except ImportError:
    from runner_lock import LOCK_FILE_PATH, SingleInstanceLock, SingleInstanceLockError

def load_tiers() -> List[str]:
    return load_tier_sequence(CONFIG_PATH)

TIERS = load_tiers()


class AtomicState:
    def __init__(self, path: str):
        self.path = path
        self.data = self.load()

    def load(self) -> Dict[str, Any]:
        if os.path.exists(self.path):
            try:
                with open(self.path, 'r') as f:
                    return json.load(f)
            except Exception as e:
                print(f"[!] Error loading state: {e}")
        return {
            "current_tier": TIERS[0] if TIERS else "tier-1",
            "mutation_count": 0,
            "total_iterations": 0,
            "history": []
        }

    def save(self) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        temp_path = self.path + ".tmp"
        with open(temp_path, 'w') as f:
            json.dump(self.data, f, indent=2)
        os.replace(temp_path, self.path)


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
            "verification": None if self.verification is None else {
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


def get_config_hash() -> str:
    if not os.path.exists(AGENT_CONFIG_PATH):
        return "unknown"
    with open(AGENT_CONFIG_PATH, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()[:8]


class AutoresearchLoop:
    """Typed execution engine for perpetual evaluation and prompt mutation loops."""

    def __init__(
        self,
        state_path: str = STATE_PATH,
        telemetry_path: str = TELEMETRY_PATH,
        benchmark_results_path: str = BENCHMARK_RESULTS_PATH,
        mutation_engine: Optional[MutationEngine] = None,
        state_dir: str = "logs/v2-state",
        benchmark_adapter: Optional[Callable[[str], Optional[Dict[str, Any]]]] = None,
        verifier_adapter: Optional[Callable[[Dict[str, Any]], VerificationResult]] = None,
        mutation_adapter: Optional[Callable[[VerificationResult, str, List[str]], Optional[MutationLogRecord]]] = None,
        mutation_surface: Optional[PolicyMutationSurface] = None,
    ):
        self.state_path = state_path
        self.telemetry_path = telemetry_path
        self.benchmark_results_path = benchmark_results_path
        self.state_manager = AtomicState(self.state_path)
        self.mutation_engine = mutation_engine or MutationEngine(results_path=benchmark_results_path)
        self.tiers = load_tiers()
        self.store = ImmutableStateStore(state_dir=state_dir)
        self.signal_lifecycle = SignalLifecycle(state_dir)
        self.telemetry_aggregator = TelemetryAggregator(store=self.store, signal_lifecycle=self.signal_lifecycle)
        self.benchmark_adapter = benchmark_adapter
        self.verifier_adapter = verifier_adapter
        self.mutation_adapter = mutation_adapter
        self.mutation_surface = mutation_surface or PolicyMutationSurface(
            frozenset(CATEGORY_TO_SEGMENT.values())
        )

    def record_signal(
        self,
        scope: Scope,
        outcome: str,
        duration_ms: int = 1000,
        retry_count: int = 0,
        verifier_category: str = "tests",
        verifier_result: str = "passed",
        model_digest: str = "sha256:0000000000000000000000000000000000000000000000000000000000000000",
        execution_profile_id: str = "codex-local",
        signal_counter: int = 100,
    ) -> Any:
        """Collect a structured v2 Signal through the canonical SignalLifecycle."""
        signal_id = f"signal-{signal_counter:03d}"
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
        )
        return self.signal_lifecycle.collect(signal)


    @property
    def state(self) -> Dict[str, Any]:
        return self.state_manager.data

    def update_telemetry(self, tier: str, summary: Dict[str, Any], config_hash: str) -> None:
        history: List[Dict[str, Any]] = []
        if os.path.exists(self.telemetry_path):
            try:
                with open(self.telemetry_path, 'r') as f:
                    history = json.load(f)
            except (OSError, json.JSONDecodeError) as exc:
                print(f"[!] Warning: could not load telemetry history ({self.telemetry_path}): {exc}. Starting fresh.")


        history.append({
            "timestamp": datetime.now().isoformat(),
            "tier": tier,
            "config_hash": config_hash,
            "success_rate": summary.get("success_rate"),
            "first_pass_rate": summary.get("first_pass_rate"),
            "avg_latency": summary.get("avg_latency_sec"),
            "total_tokens": summary.get("total_tokens")
        })
        
        log_dir = os.path.dirname(self.telemetry_path)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)
        with open(self.telemetry_path, 'w') as f:
            json.dump(history, f, indent=2)

    def run_benchmark(self, tier: str) -> Optional[Dict[str, Any]]:
        if self.benchmark_adapter is not None:
            return self.benchmark_adapter(tier)
        print(f"[*] Starting benchmark for {tier}...")
        start_time = time.time()
        swarm_mode = os.getenv("MIGHTY_MOUSE_SWARM_MODE", "swarm")
        concurrency = os.getenv("MIGHTY_MOUSE_CONCURRENCY", "2")
        cmd = [sys.executable, "eval/solve_benchmark.py", "--tier", tier, "--mode", swarm_mode, "--concurrency", concurrency]
        env = {**os.environ, "MIGHTY_MOUSE_RUNNER_LOCK_HELD": "1"}
        result = subprocess.run(cmd, capture_output=True, text=True, env=env)
        
        if result.returncode != 0:
            print(f"[!] Benchmark runner failed for {tier}:")
            print(result.stdout)
            print(result.stderr)
            return None
        
        if os.path.exists(self.benchmark_results_path):
            mtime = os.path.getmtime(self.benchmark_results_path)
            if mtime < start_time:
                print("[!] benchmark_results.json is stale. Skipping cycle.")
                return None
                
            with open(self.benchmark_results_path, 'r') as f:
                return json.load(f)
        return None

    def run_single_cycle(self) -> CycleResult:
        current_tier = self.state["current_tier"]
        config_hash = get_config_hash()
        
        print(f"\n--- Cycle Start: {datetime.now().isoformat()} ---")
        print(f"[*] Iteration: {self.state['total_iterations'] + 1}")
        print(f"[*] Current Tier: {current_tier}")
        print(f"[*] Config Hash: {config_hash}")
        print(f"[*] Mutation Count: {self.state['mutation_count']}")
        
        bench_data = self.run_benchmark(current_tier)
        if not bench_data:
            print("[!] No benchmark data received.")
            return CycleResult(status="retry_needed", tier=current_tier, state=dict(self.state))

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
        
        cycle_scope = Scope(
            mode=Mode.AGENTIC,
            repository="JOHNNYMACONNY/mighty-mouse",
            task_category=TaskCategory.MAINTENANCE,
            model_class="local-small",
        )
        cycle_outcome = "passed" if pass_rate >= 50.0 else "failed"
        signal_receipt = self.record_signal(
            scope=cycle_scope,
            outcome=cycle_outcome,
            signal_counter=max(1, self.state["total_iterations"]),
        )

        pinned_tier = os.getenv("MIGHTY_MOUSE_PIN_TIER")
        mutation_decision = None
        circuit_breaker_open = False
        if pinned_tier and pinned_tier in self.tiers:
            self.state["current_tier"] = pinned_tier
            print(f"[!] Tier Pinned: maintaining {pinned_tier} per user Pin override.")
            self.state["mutation_count"] = 0
        elif pass_rate >= 90:
            print("[+] Escalation criteria met (>=90%).")
            self.state["mutation_count"] = 0
            current_idx = self.tiers.index(current_tier) if current_tier in self.tiers else 0
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
                print("[!] Circuit breaker triggered: 3 consecutive failing mutation cycles.")
                current_idx = self.tiers.index(current_tier) if current_tier in self.tiers else 0
                if current_idx > 0:
                    self.state["current_tier"] = self.tiers[current_idx - 1]
                    print(f"[!] Dropping back to {self.state['current_tier']}")
                else:
                    print("[!] Already at lowest tier. Staying here.")
                self.state["mutation_count"] = 0
            else:
                print(f"[*] Triggering in-process mutation cycle (Attempt {self.state['mutation_count']}/3)...")
                # Direct typed in-process execution instead of subprocess
                replay_tiers = get_replay_tiers(current_tier)
                if self.mutation_adapter is not None:
                    record = self.mutation_adapter(verification, current_tier, replay_tiers)
                else:
                    record = self.mutation_engine.execute_mutation_cycle(
                        current_tier=current_tier,
                        replay_tiers=replay_tiers,
                        mutation_surface=self.mutation_surface,
                        verification_result=verification,
                    )
                mutation_decision = getattr(record, "decision", None)
                print(f"[*] Mutation cycle finished. Record decision: {getattr(record, 'decision', record if record else 'None')}")
        else:
            print("[*] Performance in stable range (50% - 90%). Maintaining current tier.")
            self.state["mutation_count"] = 0

        self.state_manager.save()


        try:
            print("[*] Generating parity report...")
            subprocess.run([sys.executable, "eval/parity_report.py"], capture_output=True)
        except Exception as e:
            logger.warning(f"Failed to generate parity report: {e}")

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

    def run_forever(self, sleep_sec: int = 10) -> None:
        print("[*] Mighty Mouse perpetual loop initiated. Press Ctrl+C to interrupt gracefully.")

        def signal_handler(sig, frame):
            print("\n[!] Graceful shutdown signal received. Saving state...")
            self.state_manager.save()
            sys.exit(0)

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        while True:
            result = self.run_single_cycle()
            if result["status"] == "retry_needed":
                print("[!] Cycle retry needed. Sleeping for 60s...")
                time.sleep(60)
            else:
                print(f"[*] Cycle complete. Sleeping for {sleep_sec}s...")
                time.sleep(sleep_sec)


EVAL_RUNNER_PID_FILE = str(LOCK_FILE_PATH)
PID_FILE = EVAL_RUNNER_PID_FILE
_ACTIVE_LOCK: SingleInstanceLock | None = None


def _acquire_pid_lock(pid_path: str = EVAL_RUNNER_PID_FILE) -> None:
    """Compatibility wrapper around the shared Harness lock."""
    global _ACTIVE_LOCK
    _ACTIVE_LOCK = SingleInstanceLock(Path(pid_path))
    try:
        _ACTIVE_LOCK.__enter__()
    except SingleInstanceLockError as exc:
        logger.error("Failed to acquire single-instance lock (%s): %s", pid_path, exc)
        _ACTIVE_LOCK = None
        sys.exit(1)


def _release_pid_lock(pid_path: str = EVAL_RUNNER_PID_FILE) -> None:
    """Release the shared Harness lock."""
    global _ACTIVE_LOCK
    if _ACTIVE_LOCK is not None:
        _ACTIVE_LOCK.__exit__(None, None, None)
        _ACTIVE_LOCK = None


def main() -> None:
    _acquire_pid_lock()
    print("=== Mighty Mouse Perpetual Loop Starting ===")
    try:
        loop = AutoresearchLoop()
        loop.run_forever()
    finally:
        _release_pid_lock()


if __name__ == "__main__":
    main()
