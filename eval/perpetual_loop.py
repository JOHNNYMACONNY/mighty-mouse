import json
import os
import subprocess
import time
import signal
import sys
import hashlib
from datetime import datetime
from typing import Dict, Any, Optional, List

# Configuration
CONFIG_PATH = "eval/evaluation_config.json"
STATE_PATH = "logs/perpetual_state.json"
TELEMETRY_PATH = "logs/metric_telemetry.json"
BENCHMARK_RESULTS_PATH = "eval/results/benchmark_results.json"
AGENT_CONFIG_PATH = "configs/mighty_mouse_v2_lean.yaml"

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_EVAL_DIR = os.path.dirname(os.path.abspath(__file__))
if _EVAL_DIR not in sys.path: sys.path.append(_EVAL_DIR)
if _REPO_ROOT not in sys.path: sys.path.append(_REPO_ROOT)

from tier_utils import load_tier_sequence
from mutation_engine import MutationEngine, ProtocolManifest

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
    """Typed execution engine for perpetual evaluation and prompt mutation loops."""

    def __init__(
        self,
        state_path: str = STATE_PATH,
        telemetry_path: str = TELEMETRY_PATH,
        benchmark_results_path: str = BENCHMARK_RESULTS_PATH,
        mutation_engine: Optional[MutationEngine] = None,
    ):
        self.state_path = state_path
        self.telemetry_path = telemetry_path
        self.benchmark_results_path = benchmark_results_path
        self.state_manager = AtomicState(self.state_path)
        self.mutation_engine = mutation_engine or MutationEngine(results_path=benchmark_results_path)
        self.tiers = load_tiers()

    @property
    def state(self) -> Dict[str, Any]:
        return self.state_manager.data

    def update_telemetry(self, tier: str, summary: Dict[str, Any], config_hash: str) -> None:
        history: List[Dict[str, Any]] = []
        if os.path.exists(self.telemetry_path):
            try:
                with open(self.telemetry_path, 'r') as f:
                    history = json.load(f)
            except Exception:
                pass
        
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
        print(f"[*] Starting benchmark for {tier}...")
        start_time = time.time()
        swarm_mode = os.getenv("MIGHTY_MOUSE_SWARM_MODE", "swarm")
        concurrency = os.getenv("MIGHTY_MOUSE_CONCURRENCY", "2")
        cmd = [sys.executable, "eval/solve_benchmark.py", "--tier", tier, "--mode", swarm_mode, "--concurrency", concurrency]
        result = subprocess.run(cmd, capture_output=True, text=True)
        
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

    def run_single_cycle(self) -> Dict[str, Any]:
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
            return {"status": "retry_needed", "tier": current_tier}

        self.state["total_iterations"] += 1
        summary = bench_data.get("summary", {})
        success_rate_str = summary.get("success_rate", "0/0")
        try:
            passed, total = map(int, success_rate_str.split('/'))
            pass_rate = (passed / total) * 100 if total > 0 else 0
        except Exception:
            pass_rate = 0.0

        print(f"[*] Results: {success_rate_str} ({pass_rate:.1f}%)")
        self.update_telemetry(current_tier, summary, config_hash)
        
        if pass_rate >= 90:
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
                manifest = self.mutation_engine.execute_mutation_cycle(current_tier=current_tier)
                print(f"[*] Mutation cycle finished. Manifest decision: {manifest.decision if manifest else 'None'}")
        else:
            print("[*] Performance in stable range (50% - 90%). Maintaining current tier.")
            self.state["mutation_count"] = 0

        self.state_manager.save()

        try:
            print("[*] Generating parity report...")
            subprocess.run([sys.executable, "eval/parity_report.py"], capture_output=True)
        except Exception as e:
            print(f"[!] Failed to generate parity report: {e}")

        return {"status": "success", "tier": current_tier, "pass_rate": pass_rate}

    def run_forever(self, sleep_sec: int = 30) -> None:
        def signal_handler(sig, frame):
            print("\n[!] Signal received. Saving state and exiting...")
            self.state_manager.save()
            sys.exit(0)

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        while True:
            result = self.run_single_cycle()
            if result.get("status") == "retry_needed":
                print(f"[!] Cycle retry needed. Sleeping for 60s...")
                time.sleep(60)
            else:
                print(f"[*] Cycle complete. Sleeping for {sleep_sec}s...")
                time.sleep(sleep_sec)


def main() -> None:
    print("=== Mighty Mouse Perpetual Loop Starting ===")
    loop = AutoresearchLoop()
    loop.run_forever()


if __name__ == "__main__":
    main()
