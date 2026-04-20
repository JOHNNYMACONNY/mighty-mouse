import json
import os

with open("logs/benchmark_results.json", 'r') as f:
    results = json.load(f)

total = len(results)
success = len([r for r in results if r['status'] == 'success'])
score = (success / total) * 100 if total > 0 else 0
print(f"{score:.2f}")
