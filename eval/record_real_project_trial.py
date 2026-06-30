#!/usr/bin/env python3
"""Append one real-project study condition and regenerate the honest report."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile


def _atomic_json(path: Path, payload: dict) -> None:
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False, encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")
        temporary = handle.name
    os.replace(temporary, path)


def _condition(args) -> dict:
    return {
        "first_try_pass": args.first_try_pass,
        "retry_rounds": args.retry_rounds,
        "scope_violations": sorted(set(args.scope_violation)),
        "duration_sec": args.duration_sec,
        "quality_score_1_to_5": args.quality_score,
        "final_commit": args.final_commit,
        "artifact_dir": args.artifact_dir,
        "review_rationale": args.review_rationale,
        "notes": args.notes,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }


def update_results(payload: dict, args) -> dict:
    shared_config = {
        "agent": args.agent,
        "model": args.model,
        "model_settings": args.model_settings,
        "environment_fingerprint": args.environment_fingerprint,
        "timeout_sec": args.timeout_sec,
        "acceptance_commands": list(args.acceptance_command),
        "allowed_paths": sorted(set(args.allowed_path)),
    }
    task = next((item for item in payload["tasks"] if item["task_id"] == args.task_id), None)
    if task is None:
        task = {
            "task_id": args.task_id,
            "project": args.project,
            "task_description": args.task_description,
            "base_commit": args.base_commit,
            "shared_config": shared_config,
            "control": None,
            "harness": None,
        }
        payload["tasks"].append(task)
    else:
        identity = (
            task["project"],
            task["task_description"],
            task["base_commit"],
            task["shared_config"],
        )
        supplied = (args.project, args.task_description, args.base_commit, shared_config)
        if identity != supplied:
            raise ValueError(
                "Paired conditions must use identical project, task description, base commit, "
                "agent, model, environment, timeout, acceptance commands, and allowed paths."
            )
    if task[args.condition] is not None and not args.replace:
        raise ValueError(f"{args.condition} condition already exists; pass --replace to overwrite it.")
    task[args.condition] = _condition(args)
    payload["tasks"] = sorted(payload["tasks"], key=lambda item: item["task_id"])
    paired = sum(item["control"] is not None and item["harness"] is not None for item in payload["tasks"])
    payload["status"] = "complete" if paired >= payload["minimum_paired_tasks"] else "collecting"
    payload["paired_tasks"] = paired
    return payload


def write_report(payload: dict, path: Path) -> None:
    paired = [item for item in payload["tasks"] if item["control"] and item["harness"]]
    lines = [
        "# Real-Project Validation",
        "",
        f"Status: **{payload['status']}**",
        "",
        "Every row is a paired control and harness run from the same recorded project commit, agent, model, and environment. Unfavorable results are retained.",
        "",
        f"Current paired tasks: **{len(paired)}/{payload['minimum_paired_tasks']} minimum**.",
    ]
    if paired:
        control_pass = sum(item["control"]["first_try_pass"] for item in paired)
        harness_pass = sum(item["harness"]["first_try_pass"] for item in paired)
        control_duration = sum(item["control"]["duration_sec"] for item in paired) / len(paired)
        harness_duration = sum(item["harness"]["duration_sec"] for item in paired) / len(paired)
        control_quality = sum(item["control"]["quality_score_1_to_5"] for item in paired) / len(paired)
        harness_quality = sum(item["harness"]["quality_score_1_to_5"] for item in paired) / len(paired)
        lines.extend([
            "",
            "| Metric | Control | Mighty Mouse |",
            "|---|---:|---:|",
            f"| First-try passes | {control_pass}/{len(paired)} | {harness_pass}/{len(paired)} |",
            f"| Total retries | {sum(item['control']['retry_rounds'] for item in paired)} | {sum(item['harness']['retry_rounds'] for item in paired)} |",
            f"| Scope violations | {sum(len(item['control']['scope_violations']) for item in paired)} | {sum(len(item['harness']['scope_violations']) for item in paired)} |",
            f"| Mean duration (seconds) | {control_duration:.1f} | {harness_duration:.1f} |",
            f"| Mean quality (1–5) | {control_quality:.2f} | {harness_quality:.2f} |",
            "",
            "## Per-task results",
            "",
            "| Task | Control first pass | Harness first pass | Retries C/H | Scope C/H | Seconds C/H | Quality C/H |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ])
        for item in paired:
            control = item["control"]
            harness = item["harness"]
            lines.append(
                f"| {item['task_id']} | {'yes' if control['first_try_pass'] else 'no'} "
                f"| {'yes' if harness['first_try_pass'] else 'no'} "
                f"| {control['retry_rounds']}/{harness['retry_rounds']} "
                f"| {len(control['scope_violations'])}/{len(harness['scope_violations'])} "
                f"| {control['duration_sec']:.1f}/{harness['duration_sec']:.1f} "
                f"| {control['quality_score_1_to_5']}/{harness['quality_score_1_to_5']} |"
            )
    if len(paired) < payload["minimum_paired_tasks"]:
        lines.extend(["", "The minimum sample has not been reached; no generalized improvement claim is made."])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Record one real-project validation condition")
    parser.add_argument("--results", default="data/evidence/real_project_results.json")
    parser.add_argument("--report", default="data/evidence/real_project_report.md")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--project", required=True)
    parser.add_argument("--task-description", required=True)
    parser.add_argument("--base-commit", required=True)
    parser.add_argument("--agent", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--model-settings", required=True)
    parser.add_argument("--environment-fingerprint", required=True)
    parser.add_argument("--timeout-sec", type=int, required=True)
    parser.add_argument("--acceptance-command", action="append", required=True)
    parser.add_argument("--allowed-path", action="append", default=[])
    parser.add_argument("--condition", choices=("control", "harness"), required=True)
    parser.add_argument("--first-try-pass", action=argparse.BooleanOptionalAction, required=True)
    parser.add_argument("--retry-rounds", type=int, required=True)
    parser.add_argument("--scope-violation", action="append", default=[])
    parser.add_argument("--duration-sec", type=float, required=True)
    parser.add_argument("--quality-score", type=int, choices=range(1, 6), required=True)
    parser.add_argument("--final-commit", required=True)
    parser.add_argument("--artifact-dir", required=True)
    parser.add_argument("--review-rationale", required=True)
    parser.add_argument("--notes", default="")
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()
    if args.retry_rounds < 0 or args.duration_sec < 0 or args.timeout_sec <= 0:
        parser.error("retry rounds and duration must be non-negative; timeout must be positive")

    results_path = Path(args.results).resolve()
    payload = json.loads(results_path.read_text(encoding="utf-8"))
    update_results(payload, args)
    _atomic_json(results_path, payload)
    write_report(payload, Path(args.report).resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
