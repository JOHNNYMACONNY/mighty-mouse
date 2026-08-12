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


from tier_utils import load_tier_sequence, parse_pass_rate  # noqa: E402
from mutation_engine import (  # noqa: E402
    CATEGORY_TO_SEGMENT,
    MutationEngine,
    MutationLogRecord,
    get_replay_tiers,
)
try:
    from .autoresearch_cycle import (
        AutoresearchCycle,
        CycleResult,
        MutationRequest,
    )
except ImportError:
    from autoresearch_cycle import (
        AutoresearchCycle,
        CycleResult,
        MutationRequest,
    )
from mighty_mouse.v2.foundation import (
    ImmutableStateStore,
    Scope,
)
from mighty_mouse.v2.signals import SignalLifecycle
from mighty_mouse.v2.seams import PolicyMutationSurface, VerificationResult
from mighty_mouse.v2.telemetry import (  # noqa: E402
    SignalAggregator,
    SignalTelemetry,
)
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


def get_config_hash() -> str:
    if not os.path.exists(AGENT_CONFIG_PATH):
        return "unknown"
    with open(AGENT_CONFIG_PATH, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()[:8]


class AutoresearchLoop:
    """Typed execution engine for bounded evaluation and mutation cycles."""

    def __init__(
        self,
        state_path: str = STATE_PATH,
        telemetry_path: str = TELEMETRY_PATH,
        benchmark_results_path: str = BENCHMARK_RESULTS_PATH,
        mutation_engine: Optional[MutationEngine] = None,
        state_dir: str = "logs/v2-state",
        benchmark_adapter: Optional[
            Callable[[str], Optional[Dict[str, Any]]]
        ] = None,
        verifier_adapter: Optional[
            Callable[[Dict[str, Any]], VerificationResult]
        ] = None,
        mutation_adapter: Optional[
            Callable[[MutationRequest], Optional[MutationLogRecord]]
        ] = None,
        mutation_surface: Optional[PolicyMutationSurface] = None,
    ):
        self.state_path = state_path
        self.telemetry_path = telemetry_path
        self.benchmark_results_path = benchmark_results_path
        self.state_manager = AtomicState(self.state_path)
        self.mutation_engine = mutation_engine or MutationEngine(
            results_path=benchmark_results_path
        )
        self.tiers = load_tiers()
        self.store = ImmutableStateStore(state_dir=state_dir)
        self.signal_lifecycle = SignalLifecycle(state_dir)
        self.signal_telemetry = SignalTelemetry(self.signal_lifecycle)
        self.telemetry_aggregator = SignalAggregator(
            store=self.store, signal_lifecycle=self.signal_lifecycle
        )
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
        model_digest: str = (
            "sha256:00000000000000000000000000000000"
            "00000000000000000000000000000000"
        ),
        execution_profile_id: str = "codex-local",
        signal_counter: int = 100,
    ) -> Any:
        """Record a structured v2 Signal through canonical SignalTelemetry."""
        return self.signal_telemetry.record(
            signal_id=f"signal-{signal_counter:03d}",
            scope=scope,
            model_digest=model_digest,
            execution_profile_id=execution_profile_id,
            outcome=outcome,
            duration_ms=duration_ms,
            retry_count=retry_count,
            verifier_category=verifier_category,
            verifier_result=verifier_result,
        )
    @property
    def state(self) -> Dict[str, Any]:
        return self.state_manager.data

    def update_telemetry(
        self, tier: str, summary: Dict[str, Any], config_hash: str
    ) -> None:
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

    def config_hash(self) -> str:
        return get_config_hash()

    def verify_benchmark(
        self, benchmark: Dict[str, Any]
    ) -> VerificationResult:
        if self.verifier_adapter is not None:
            return self.verifier_adapter(benchmark)

        summary = benchmark.get("summary", {})
        pass_rate = parse_pass_rate(summary) * 100.0
        return VerificationResult(
            passed=pass_rate >= 100.0,
            score=pass_rate / 100.0,
            details={"verifier_category": "LOGIC"},
            verdict_category="PASS" if pass_rate >= 100.0 else "FAIL",
        )

    def replay_tiers(self, tier: str) -> List[str]:
        return get_replay_tiers(tier)

    def execute_mutation(self, request: MutationRequest) -> Any:
        if self.mutation_adapter is not None:
            return self.mutation_adapter(request)

        return self.mutation_engine.execute_mutation_cycle(
            current_tier=request.current_tier,
            replay_tiers=list(request.replay_tiers),
            mutation_surface=self.mutation_surface,
            verification_result=request.verification,
        )

    def save_state(self) -> None:
        self.state_manager.save()

    def run_parity_report(self) -> None:
        self._run_parity_report()

    def build_cycle(self) -> AutoresearchCycle:
        """Build one independently callable cycle over current loop state."""
        return AutoresearchCycle(
            state=self.state,
            tiers=self.tiers,
            operations=self,
        )

    def run_single_cycle(self) -> CycleResult:
        """Run one bounded cycle through canonical AutoresearchCycle."""
        return self.build_cycle().run()

    def _run_parity_report(self) -> None:
        try:
            print("[*] Generating parity report...")
            subprocess.run(
                [sys.executable, "eval/parity_report.py"], capture_output=True
            )
        except Exception as exc:
            logger.warning(f"Failed to generate parity report: {exc}")

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
