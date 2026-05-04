import json
import os
import subprocess
import sys

def get_success_count(tier="tier_1"):
    # Run the benchmark
    cmd = f"python3 eval/solve_benchmark.py --tier {tier}"
    subprocess.run(cmd, shell=True, capture_output=True)
    
    # Read the results
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

if __name__ == "__main__":
    tier = sys.argv[1] if len(sys.argv) > 1 else "tier_1"
    print(get_success_count(tier))
