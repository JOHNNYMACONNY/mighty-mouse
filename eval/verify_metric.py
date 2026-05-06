import json
import os
import subprocess
import sys

# SECURE CORE - The model is forbidden from modifying this core validation logic
def _secure_get_success_count(tier="tier_1"):
    cmd = f"python3 eval/solve_benchmark.py --tier {tier}"
    subprocess.run(cmd, shell=True, capture_output=True)
    
    results_path = "eval/results/benchmark_results.json"
    if not os.path.exists(results_path):
        return 0
        
    try:
        with open(results_path, 'r') as f:
            data = json.load(f)
            success_rate = data.get("summary", {}).get("success_rate", "0/0")
            success_count = int(success_rate.split('/')[0])
            return success_count
    except Exception:
        return 0

# MUTABLE HOOK - The model is allowed to modify this function to add telemetry, parse ASTs, etc.
def extend_telemetry(tier, results_path):
    if not os.path.exists(results_path):
        return
    try:
        with open(results_path, 'r') as f:
            data = json.load(f)
        
        # Calculate First Pass Rate
        results = data.get("results", [])
        if not results: return
        
        first_pass_count = len([r for r in results if r.get("attempts", 1) == 1 and r.get("status") == "success"])
        total_count = len(results)
        
        print(f"[Telemetry] Tier: {tier}")
        print(f"[Telemetry] First Pass Rate: {first_pass_count}/{total_count} ({first_pass_count/total_count:.1%})")
        
        # Save to persistent metric log
        log_file = "logs/metric_telemetry.json"
        history = []
        if os.path.exists(log_file):
            try:
                with open(log_file, 'r') as f:
                    history = json.load(f)
            except Exception: pass
        
        history.append({
            "timestamp": data.get("summary", {}).get("timestamp"),
            "tier": tier,
            "success_rate": data.get("summary", {}).get("success_rate"),
            "first_pass_rate": f"{first_pass_count}/{total_count}"
        })
        
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        with open(log_file, 'w') as f:
            json.dump(history, f, indent=2)
            
    except Exception as e:
        print(f"[Telemetry Error] {e}")

def get_success_count(tier="tier_1"):
    count = _secure_get_success_count(tier)
    # Fire the telemetry hook after execution
    extend_telemetry(tier, "eval/results/benchmark_results.json")
    return count

if __name__ == "__main__":
    tier = sys.argv[1] if len(sys.argv) > 1 else "tier_1"
    print(get_success_count(tier))
