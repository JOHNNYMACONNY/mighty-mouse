import json, os, argparse

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tier", help="Filter by tier (e.g. 1, 2, 3, 4, 5)")
    args = parser.parse_args()

    results_path = "logs/benchmark_results.json"
    if not os.path.exists(results_path):
        print("0.00")
        return

    with open(results_path, 'r') as f:
        res = json.load(f)

    if args.tier:
        # Tier logic: 100-tasks-per-tier (approx)
        # Tier 1: 1-100, Tier 2: 101-200, Tier 3: 201-300, Tier 4: 301-400, Tier 5: 401+
        t = int(args.tier)
        filtered = []
        for r in res:
            try:
                # Extract numeric suffix from task_XXX
                parts = r['task_id'].split('_')
                idx = int(parts[1])
                if (t-1)*100 < idx <= t*100:
                    filtered.append(r)
                elif t == 5 and idx > 400: # Catch-all for Tier 5
                    filtered.append(r)
            except: continue
        res = filtered

    if not res:
        print("0.00")
        return

    success = len([r for r in res if r['status'] == 'success'])
    total = len(res)
    print(f"{(success/total)*100:.2f}")

if __name__ == "__main__": main()
