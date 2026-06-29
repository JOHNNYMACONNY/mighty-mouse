import json
import os
import subprocess
import time
import signal
import sys
import hashlib
from datetime import datetime

# Configuration
CONFIG_PATH = "eval/evaluation_config.json"
STATE_PATH = "logs/perpetual_state.json"
TELEMETRY_PATH = "logs/metric_telemetry.json"
BENCHMARK_RESULTS_PATH = "logs/benchmark_results.json"
MUTATION_ENGINE_PATH = "eval/mutation_engine.py"
AGENT_CONFIG_PATH = "configs/mighty_mouse_v2_lean.yaml"

TIERS = ["tier_1", "tier_overnight", "tier_3", "tier_4", "tier_5", "tier_6", "tier_7"]

class AtomicState:
    def __init__(self, path):
        self.path = path
        self.data = self.load()

    def load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, 'r') as f:
                    return json.load(f)
            except Exception as e:
                print(f"[!] Error loading state: {e}")
        return {
            "current_tier": TIERS[0],
            "mutation_count": 0,
            "total_iterations": 0,
            "history": []
        }

    def save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        temp_path = self.path + ".tmp"
        with open(temp_path, 'w') as f:
            json.dump(self.data, f, indent=2)
        os.replace(temp_path, self.path)

def get_config_hash():
    if not os.path.exists(AGENT_CONFIG_PATH):
        return "unknown"
    with open(AGENT_CONFIG_PATH, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()[:8]

def update_telemetry(tier, summary, config_hash):
    history = []
    if os.path.exists(TELEMETRY_PATH):
        try:
            with open(TELEMETRY_PATH, 'r') as f:
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
    
    with open(TELEMETRY_PATH, 'w') as f:
        json.dump(history, f, indent=2)

def run_benchmark(tier):
    print(f"[*] Starting benchmark for {tier}...")
    start_time = time.time()
    cmd = [sys.executable, "eval/run_parallel.py", "--tier", tier]
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        print(f"[!] Benchmark runner failed for {tier}:")
        print(result.stdout)
        print(result.stderr)
        return None
    
    if os.path.exists(BENCHMARK_RESULTS_PATH):
        # Temporal Guard: Ensure file is fresh
        mtime = os.path.getmtime(BENCHMARK_RESULTS_PATH)
        if mtime < start_time:
            print("[!] benchmark_results.json is stale. Skipping cycle.")
            return None
            
        with open(BENCHMARK_RESULTS_PATH, 'r') as f:
            return json.load(f)
    return None

def signal_handler(sig, frame):
    print("\n[!] Signal received. Saving state and exiting...")
    global state_manager
    if 'state_manager' in globals():
        state_manager.save()
    sys.exit(0)

def main():
    print("=== Mighty Mouse Perpetual Loop Starting ===")
    global state_manager
    state_manager = AtomicState(STATE_PATH)
    state = state_manager.data
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    while True:
        current_tier = state["current_tier"]
        config_hash = get_config_hash()
        
        print(f"\n--- Cycle Start: {datetime.now().isoformat()} ---")
        print(f"[*] Iteration: {state['total_iterations'] + 1}")
        print(f"[*] Current Tier: {current_tier}")
        print(f"[*] Config Hash: {config_hash}")
        print(f"[*] Mutation Count: {state['mutation_count']}")
        
        bench_data = run_benchmark(current_tier)
        if not bench_data:
            print("[!] No benchmark data received. Retrying in 60s...")
            time.sleep(60)
            continue
        
        state["total_iterations"] += 1
        summary = bench_data.get("summary", {})
        success_rate_str = summary.get("success_rate", "0/0")
        passed, total = map(int, success_rate_str.split('/'))
        pass_rate = (passed / total) * 100 if total > 0 else 0
        
        print(f"[*] Results: {success_rate_str} ({pass_rate:.1f}%)")
        
        update_telemetry(current_tier, summary, config_hash)
        
        # Decision Logic
        if pass_rate >= 90:
            print("[+] Escalation criteria met (>=90%).")
            state["mutation_count"] = 0
            # Move to next tier
            current_idx = TIERS.index(current_tier)
            if current_idx < len(TIERS) - 1:
                state["current_tier"] = TIERS[current_idx + 1]
                print(f"[+] Escalating to {state['current_tier']}")
            else:
                print("[*] Already at highest tier. Maintaining.")
        elif pass_rate < 50:
            print("[-] Mutation criteria met (<50%).")
            state["mutation_count"] += 1
            
            if state["mutation_count"] >= 3:
                print("[!] Circuit breaker triggered: 3 consecutive failing mutation cycles.")
                # Drop one tier
                current_idx = TIERS.index(current_tier)
                if current_idx > 0:
                    state["current_tier"] = TIERS[current_idx - 1]
                    print(f"[!] Dropping back to {state['current_tier']}")
                else:
                    print("[!] Already at lowest tier. Staying here.")
                state["mutation_count"] = 0
            else:
                print(f"[*] Triggering mutation cycle (Attempt {state['mutation_count']}/3)...")
                subprocess.run([sys.executable, MUTATION_ENGINE_PATH])
        else:
            print("[*] Performance in stable range (50% - 90%). Maintaining current tier.")
            # Note: The plan says "Retry once; then trigger mutation if score stagnant."
            # For Phase 32 simplification, we'll just maintain.
            state["mutation_count"] = 0 
        
        state_manager.save()
        
        # Phase 34: Generate Parity Report
        try:
            print("[*] Generating parity report...")
            subprocess.run([sys.executable, "eval/parity_report.py"])
        except Exception as e:
            print(f"[!] Failed to generate parity report: {e}")
            
        print(f"[*] Cycle complete. Sleeping for 30s...")
        time.sleep(30)

if __name__ == "__main__":
    main()
