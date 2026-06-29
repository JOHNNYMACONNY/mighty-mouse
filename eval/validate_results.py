import json
import os
import pandas as pd
from datetime import datetime

import os
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_BASELINE = os.path.join(REPO_ROOT, "logs/validation_baseline.jsonl")
LOG_LEAN = os.path.join(REPO_ROOT, "logs/validation_lean.jsonl")
OUTPUT_MD = os.path.join(REPO_ROOT, "eval/results/validation_report.md")

HARD_TASKS = ["task_011_realtime_decorator_ratelimiter", "task_015_async_service_circuitbreaker"]
REPLAY_GATE_TASKS = [
    "task_001_legacy_registry_ratelimiter",
    "task_002_stream_cache_validator",
    "task_003_legacy_link_circuitbreaker",
    "task_004_network_link_validator",
    "task_005_network_iterator_retry"
]

def load_results(path):
    results = []
    if os.path.exists(path):
        with open(path, 'r') as f:
            for line in f:
                if line.strip():
                    results.append(json.loads(line))
    return results

def summarize_variant(name, results):
    if not results:
        return {
            "name": name,
            "pass_rate": "0%",
            "avg_time_success": 0,
            "timeouts": 0,
            "logic_fails": 0,
            "other_fails": 0,
            "replay_pass": False,
            "hard_pass_count": 0
        }
    
    df = pd.DataFrame(results)
    total = len(df)
    passed = len(df[df['status'] == 'success'])
    pass_rate = (passed / total) * 100 if total > 0 else 0
    
    avg_time_success = df[df['status'] == 'success']['wall_clock_time'].mean() if passed > 0 else 0
    
    timeouts = len(df[df['category'] == 'TIMEOUT'])
    logic_fails = len(df[df['category'] == 'LOGIC'])
    other_fails = total - passed - timeouts - logic_fails
    
    replay_results = df[df['task_id'].isin(REPLAY_GATE_TASKS)]
    replay_pass = len(replay_results[replay_results['status'] == 'success']) == len(REPLAY_GATE_TASKS)
    
    hard_results = df[df['task_id'].isin(HARD_TASKS)]
    hard_pass_count = len(hard_results[hard_results['status'] == 'success'])
    
    return {
        "name": name,
        "pass_rate": f"{pass_rate:.1f}% ({passed}/{total})",
        "avg_time_success": round(avg_time_success, 2),
        "timeouts": timeouts,
        "logic_fails": logic_fails,
        "other_fails": other_fails,
        "replay_pass": replay_pass,
        "hard_pass_count": hard_pass_count
    }

def generate_report():
    baseline_res = load_results(LOG_BASELINE)
    lean_res = load_results(LOG_LEAN)
    
    s_base = summarize_variant("Baseline v1", baseline_res)
    s_lean = summarize_variant("Lean Protocol", lean_res)
    
    # Delta Calculation
    time_delta = 0
    if s_base['avg_time_success'] > 0:
        time_delta = ((s_base['avg_time_success'] - s_lean['avg_time_success']) / s_base['avg_time_success']) * 100

    recommendation = "INCONCLUSIVE"
    if not lean_res:
        recommendation = "RETORNO"
    else:
        # Promotion logic
        passed_replay = s_lean['replay_pass']
        pass_rate_ok = float(s_lean['pass_rate'].split('%')[0]) >= float(s_base['pass_rate'].split('%')[0])
        latency_ok = time_delta >= 20
        no_parser_creep = s_lean['other_fails'] <= s_base['other_fails']
        
        if passed_replay and pass_rate_ok and latency_ok and no_parser_creep:
            recommendation = "PROMOTE"
        elif not passed_replay:
            recommendation = "REJECT (Replay Gate Failed)"
        elif not latency_ok:
            recommendation = "REJECT (Latency target not met)"
        else:
            recommendation = "RETEST / DISCUSS"

    md = f"""# Validation Report: Lean Protocol Candidate

**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## Recommendation: {recommendation}

| Metric | Baseline v1 | Lean Protocol | Delta |
|---|---|---|---|
| **Pass Rate** | {s_base['pass_rate']} | {s_lean['pass_rate']} | - |
| **Avg Time (Success)** | {s_base['avg_time_success']}s | {s_lean['avg_time_success']}s | {time_delta:.1f}% |
| **TIMEOUT Count** | {s_base['timeouts']} | {s_lean['timeouts']} | - |
| **LOGIC Fails** | {s_base['logic_fails']} | {s_lean['logic_fails']} | - |
| **Other Fails** | {s_base['other_fails']} | {s_lean['other_fails']} | - |
| **Replay Gate (Tier 1)** | {'PASS' if s_base['replay_pass'] else 'FAIL'} | {'PASS' if s_lean['replay_pass'] else 'FAIL'} | - |
| **Hard Tasks (Horizon)** | {s_base['hard_pass_count']}/2 | {s_lean['hard_pass_count']}/2 | - |

## Success Criteria Verification
- [ ] Lean pass rate >= Baseline: {'YES' if float(s_lean['pass_rate'].split('%')[0]) >= float(s_base['pass_rate'].split('%')[0]) else 'NO'}
- [ ] Lean latency reduction >= 20%: {'YES' if time_delta >= 20 else 'NO'}
- [ ] Tier 1 Replay Gate: {'PASS' if s_lean['replay_pass'] else 'FAIL'}
- [ ] No regression in Parser/Scope/Verification: {'PASS' if s_lean['other_fails'] <= s_base['other_fails'] else 'FAIL'}

## Raw Task Comparison
"""
    
    all_tasks = set([r['task_id'] for r in baseline_res] + [r['task_id'] for r in lean_res])
    md += "| Task ID | Baseline | Lean | Time Diff |\n|---|---|---|---|\n"
    
    b_dict = {r['task_id']: r for r in baseline_res}
    l_dict = {r['task_id']: r for r in lean_res}
    
    for tid in sorted(list(all_tasks)):
        b = b_dict.get(tid, {})
        l = l_dict.get(tid, {})
        
        b_str = f"{b.get('status', 'N/A')} ({b.get('wall_clock_time', 0)}s)"
        l_str = f"{l.get('status', 'N/A')} ({l.get('wall_clock_time', 0)}s)"
        
        diff = ""
        if b.get('status') == 'success' and l.get('status') == 'success':
            d = ((b['wall_clock_time'] - l['wall_clock_time']) / b['wall_clock_time']) * 100
            diff = f"{d:.1f}%"
            
        md += f"| {tid} | {b_str} | {l_str} | {diff} |\n"

    md += """
---
*Note: Successful tasks only for latency deltas. Hard Reasoning Horizon tasks are task_011 and task_015.*
"""
    
    os.makedirs(os.path.dirname(OUTPUT_MD), exist_ok=True)
    with open(OUTPUT_MD, 'w') as f:
        f.write(md)
    print(f"[+] Validation report generated at {OUTPUT_MD}")

if __name__ == "__main__":
    generate_report()
