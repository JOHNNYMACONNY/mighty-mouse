import json
import os
import sys

def score():
    log_file = "logs/benchmark_results.json"
    if not os.path.exists(log_file):
        print("0.0") # Baseline failure
        return

    try:
        with open(log_file, 'r') as f:
            results = json.load(f)
    except Exception as e:
        print("0.0")
        return

    if not results:
        print("0.0")
        return

    total = len(results)
    passed = sum(1 for r in results if r.get('status') == 'success')
    
    # Primary Metric: Success Rate %
    success_rate = (passed / total) * 100
    
    # Print only the number for autoresearch to capture
    print(f"{success_rate:.2f}")

if __name__ == "__main__":
    score()
