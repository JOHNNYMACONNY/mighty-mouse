import argparse
import json
import os
import sys
from datetime import datetime
from run_parallel import run_task

def main():
    parser = argparse.ArgumentParser(description="Mighty Mouse A/B Validation Runner")
    parser.add_argument("--task", help="Single task file path")
    parser.add_argument("--suite", help="JSON suite file path containing multiple tasks")
    parser.add_argument("--skill", required=True, help="Skill ID to test")
    parser.add_argument("--config", default="configs/mighty_mouse_v2_lean.yaml")
    parser.add_argument("--trials", type=int, default=1)
    parser.add_argument("--phase", default="55", help="Phase ID for naming artifacts")
    parser.add_argument("--output-dir", default="eval/results/ab_validation", help="Directory to save A/B validation results")
    args = parser.parse_args()

    if not args.task and not args.suite:
        print("Error: Either --task or --suite must be provided.")
        sys.exit(1)

    tasks = []
    if args.task:
        tasks.append(args.task)
    if args.suite:
        with open(args.suite, "r") as f:
            suite_data = json.load(f)
            tasks.extend(suite_data.get("tasks", []))

    all_comparisons = []
    
    print(f"[*] Starting A/B Validation for skill: {args.skill} (Phase {args.phase})")
    print(f"[*] Total tasks: {len(tasks)}")
    
    report_dir = os.path.join(args.output_dir, f"phase_{args.phase}")
    os.makedirs(report_dir, exist_ok=True)

    for task_path in tasks:
        print(f"\n{'-'*60}")
        print(f"[*] Task: {task_path}")
        
        # 1. Run Baseline
        print(f"[*] Running Baseline (v2_lean)...")
        baseline_res = run_task(task_path, variant="lean", config_path=args.config, trials=args.trials, cleanup=True, skills=None)
        
        # 2. Run with Skill
        print(f"[*] Running with Skill Overlay: {args.skill}...")
        skill_res = run_task(task_path, variant="lean", config_path=args.config, trials=args.trials, cleanup=True, skills=args.skill)
        
        # Helper to extract telemetry from last round
        def extract_run_telemetry(res):
            last_round = res.get("rounds", [])[-1] if res.get("rounds") else {}
            meta = last_round.get("run_metadata", {})
            return {
                "auto_injected": meta.get("auto_injected", False),
                "injection_reason": meta.get("injection_reason"),
                "timeout": last_round.get("timeout", False),
                "scope_status": res.get("telemetry", {}).get("scope_status", "UNKNOWN")
            }

        b_telemetry = extract_run_telemetry(baseline_res)
        s_telemetry = extract_run_telemetry(skill_res)

        comparison = {
            "metadata": {
                "task_id": baseline_res["task_id"],
                "skill_id": args.skill,
                "timestamp": datetime.now().isoformat(),
                "phase": args.phase
            },
            "baseline": {
                "status": baseline_res["status"],
                "category": baseline_res["category"],
                "latency": baseline_res["latency_seconds"],
                "skill_ids": baseline_res.get("skill_ids", []),
                "overlay_enabled": baseline_res.get("overlay_enabled", False),
                "auto_injected": b_telemetry["auto_injected"],
                "injection_reason": b_telemetry["injection_reason"],
                "timeout": b_telemetry["timeout"],
                "scope_status": b_telemetry["scope_status"]
            },
            "skill_overlay": {
                "status": skill_res["status"],
                "category": skill_res["category"],
                "latency": skill_res["latency_seconds"],
                "skill_ids": skill_res.get("skill_ids", []),
                "overlay_enabled": skill_res.get("overlay_enabled", False),
                "auto_injected": s_telemetry["auto_injected"],
                "injection_reason": s_telemetry["injection_reason"],
                "timeout": s_telemetry["timeout"],
                "scope_status": s_telemetry["scope_status"]
            }
        }
        all_comparisons.append(comparison)
        
        print(f"BASELINE:      {comparison['baseline']['status']} ({comparison['baseline']['category']}) in {comparison['baseline']['latency']}s [Skills: {comparison['baseline']['skill_ids']}]")
        print(f"SKILL OVERLAY: {comparison['skill_overlay']['status']} ({comparison['skill_overlay']['category']}) in {comparison['skill_overlay']['latency']}s [Skills: {comparison['skill_overlay']['skill_ids']}]")

        # Save individual report
        report_path = os.path.join(report_dir, f"ab_{comparison['metadata']['task_id']}_{args.skill}.json")
        with open(report_path, "w") as f:
            json.dump(comparison, f, indent=2)

    # Global Summary
    print("\n" + "="*60)
    print(f"PHASE {args.phase} VALIDATION SUMMARY")
    print("="*60)
    
    regressions = 0
    wins = 0
    total_latency_baseline = 0
    total_latency_skill = 0
    stacking_detected = False
    
    for comp in all_comparisons:
        b = comp["baseline"]
        s = comp["skill_overlay"]
        
        if b["status"] == "success" and s["status"] != "success":
            regressions += 1
        
        if b["status"] != "success" and s["status"] == "success":
            wins += 1
            
        total_latency_baseline += b["latency"]
        total_latency_skill += s["latency"]

        # Stacking detection
        if "S1-STATE" in s["skill_ids"] and args.skill == "S2-STREAM":
            stacking_detected = True

    avg_latency_delta = (total_latency_skill - total_latency_baseline) / total_latency_baseline if total_latency_baseline > 0 else 0
    
    print(f"Total Tasks: {len(all_comparisons)}")
    print(f"Wins: {wins}")
    print(f"Regressions: {regressions}")
    print(f"Avg Latency Delta: {avg_latency_delta*100:.2f}%")
    if stacking_detected:
        print("[!] CRITICAL: Skill Stacking Detected (S1-STATE found during S2 validation)")
    print("="*60)
    
    # Save aggregate report
    aggregate_report = {
        "summary": {
            "phase": args.phase,
            "total_tasks": len(all_comparisons),
            "wins": wins,
            "regressions": regressions,
            "avg_latency_delta": avg_latency_delta,
            "stacking_detected": stacking_detected,
            "timestamp": datetime.now().isoformat()
        },
        "results": all_comparisons
    }
    aggregate_path = os.path.join(report_dir, f"aggregate_phase_{args.phase}.json")
    with open(aggregate_path, "w") as f:
        json.dump(aggregate_report, f, indent=2)
    print(f"[*] Aggregate report saved to {aggregate_path}")

if __name__ == "__main__":
    main()
