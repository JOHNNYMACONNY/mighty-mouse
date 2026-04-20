import json
import os
if os.path.exists("logs/benchmark_results.json"):
    with open("logs/benchmark_results.json", 'r') as f:
        res = json.load(f)
    success = len([r for r in res if r['status'] == 'success'])
    total = len(res)
    print(f"{(success/total)*100:.2f}")
else:
    print("0.00")
