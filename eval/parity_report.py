import json
import os
from datetime import datetime

RESULTS_PATH = "logs/benchmark_results.json"
REFERENCE_PATH = "eval/results/frontier_reference.json"
TELEMETRY_PATH = "logs/metric_telemetry.json"
OUTPUT_PATH = "eval/results/frontier_delta.md"

def load_json(path, default=None):
    if os.path.exists(path):
        try:
            with open(path, 'r') as f:
                return json.load(f)
        except Exception:
            pass
    return default

def calculate_pass_rate(summary):
    if not summary: return 0.0
    rate_str = summary.get("success_rate", "0/0")
    try:
        passed, total = map(int, rate_str.split('/'))
        return passed / total if total > 0 else 0.0
    except:
        return 0.0

def generate_report():
    results = load_json(RESULTS_PATH)
    reference = load_json(REFERENCE_PATH, {"references": []})
    telemetry = load_json(TELEMETRY_PATH, [])
    
    if not results:
        print("[!] No benchmark results found to generate report.")
        return

    summary = results.get("summary", {})
    current_rate = calculate_pass_rate(summary)
    timestamp = summary.get("timestamp", datetime.now().isoformat())
    
    # Find closest reference
    closest_ref = None
    min_diff = float('inf')
    for ref in reference["references"]:
        diff = abs(current_rate - ref["pass_rate"])
        if diff < min_diff:
            min_diff = diff
            closest_ref = ref
    
    parity_score = (current_rate / closest_ref["pass_rate"]) * 100 if closest_ref and closest_ref["pass_rate"] > 0 else 0
    
    # Trend line (last 10 runs)
    trend = telemetry[-10:] if telemetry else []
    
    md = f"""# Frontier Delta Report: Mighty Mouse vs. Baseline

**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**Source of Truth**: Mighty Mouse Autonomous Benchmark Suite
**Calibration Reference**: Static LiveCodeBench Data

## Local Model Performance (`gemma4:e4b`)

| Metric | Current Value |
|---|---|
| **Tier** | {summary.get('tier', 'Unknown')} |
| **Pass Rate** | {current_rate:.1%} ({summary.get('success_rate')}) |
| **First Pass Rate** | {summary.get('first_pass_rate', 'N/A')} |
| **Avg Latency** | {summary.get('avg_latency_sec', 0):.2f}s |
| **Total Tokens** | {summary.get('total_tokens', 0)} |

## Frontier Parity

| Reference Model | Reference Pass Rate | Local Parity |
|---|---|---|
"""
    for ref in reference["references"]:
        p = (current_rate / ref["pass_rate"]) * 100 if ref["pass_rate"] > 0 else 0
        md += f"| {ref['model']} | {ref['pass_rate']:.1%} | {p:.1f}% |\n"

    md += f"""
---
**Primary Calibration Point**: {closest_ref['model'] if closest_ref else 'N/A'}
**Parity Score**: {parity_score:.1f}%

## Trend Analysis (Last 10 Cycles)

| Timestamp | Tier | Pass Rate | Parity |
|---|---|---|---|
"""
    for entry in trend:
        trate = calculate_pass_rate(entry)
        tparity = (trate / closest_ref["pass_rate"]) * 100 if closest_ref and closest_ref["pass_rate"] > 0 else 0
        md += f"| {entry.get('timestamp')[:16]} | {entry.get('tier')} | {entry.get('success_rate')} | {tparity:.1f}% |\n"

    md += """
---
*Note: This report is generated automatically at the end of each perpetual loop cycle. LiveCodeBench scores are used as a static ceiling for gap-tracking only.*
"""
    
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, 'w') as f:
        f.write(md)
    print(f"[+] Parity report generated at {OUTPUT_PATH}")

if __name__ == "__main__":
    generate_report()
