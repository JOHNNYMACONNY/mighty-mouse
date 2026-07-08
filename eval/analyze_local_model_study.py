#!/usr/bin/env python3
"""Aggregate paired local-model study summaries without inflating claims."""

from __future__ import annotations

import argparse
import json
import math
import statistics
from pathlib import Path
from typing import Any


CONDITIONS = ("gemma_raw", "gemma_mighty_mouse", "reference_raw")


def _exact_mcnemar_p(raw_only: int, mighty_only: int) -> float | None:
    discordant = raw_only + mighty_only
    if discordant == 0:
        return None
    smaller = min(raw_only, mighty_only)
    lower_tail = sum(math.comb(discordant, index) for index in range(smaller + 1)) / (2**discordant)
    return min(1.0, 2 * lower_tail)


def load_summaries(run_dirs: list[Path], *, allow_pilot: bool = False) -> list[dict[str, Any]]:
    summaries = []
    task_ids = set()
    for run_dir in run_dirs:
        path = run_dir / "summary.json"
        if not path.is_file():
            raise ValueError(f"Missing summary.json: {run_dir}")
        summary = json.loads(path.read_text(encoding="utf-8"))
        study_class = summary.get("study_class")
        if study_class == "unscored_pilot" and not allow_pilot:
            raise ValueError("Pilot results are unscored; pass --allow-pilot only for runner diagnostics")
        if study_class not in {"unscored_pilot", "scored"}:
            raise ValueError(f"Unsupported study_class in {path}: {study_class}")
        task_id = summary.get("task_id")
        if not task_id or task_id in task_ids:
            raise ValueError(f"Missing or duplicate task_id: {task_id}")
        task_ids.add(task_id)
        missing = sorted(set(CONDITIONS) - set(summary.get("results", {})))
        if missing:
            raise ValueError(f"Task {task_id} is missing conditions: {', '.join(missing)}")
        summaries.append(summary)
    if not summaries:
        raise ValueError("At least one run directory is required")
    return summaries


def analyze(summaries: list[dict[str, Any]]) -> dict[str, Any]:
    task_count = len(summaries)
    condition_metrics = {}
    for condition in CONDITIONS:
        rows = [summary["results"][condition] for summary in summaries]
        passes = sum(bool(row["passed"]) for row in rows)
        condition_metrics[condition] = {
            "passes": passes,
            "tasks": task_count,
            "completion_rate": passes / task_count,
            "median_duration_seconds": statistics.median(float(row["duration_seconds"]) for row in rows),
            "median_total_tokens": statistics.median(int(row["total_tokens"]) for row in rows),
            "median_tool_calls": statistics.median(int(row["tool_calls"]) for row in rows),
        }

    raw_only = 0
    mighty_only = 0
    both_pass = 0
    both_fail = 0
    per_task = []
    for summary in summaries:
        raw = bool(summary["results"]["gemma_raw"]["passed"])
        mighty = bool(summary["results"]["gemma_mighty_mouse"]["passed"])
        reference = bool(summary["results"]["reference_raw"]["passed"])
        if raw and mighty:
            both_pass += 1
        elif raw:
            raw_only += 1
        elif mighty:
            mighty_only += 1
        else:
            both_fail += 1
        per_task.append({
            "task_id": summary["task_id"],
            "gemma_raw": raw,
            "gemma_mighty_mouse": mighty,
            "reference_raw": reference,
        })

    raw_rate = condition_metrics["gemma_raw"]["completion_rate"]
    mighty_rate = condition_metrics["gemma_mighty_mouse"]["completion_rate"]
    reference_rate = condition_metrics["reference_raw"]["completion_rate"]
    denominator = reference_rate - raw_rate
    gap_closure = (mighty_rate - raw_rate) / denominator if denominator > 0 else None
    classes = sorted({summary["study_class"] for summary in summaries})
    return {
        "schema_version": 1,
        "study_classes": classes,
        "task_count": task_count,
        "conditions": condition_metrics,
        "gemma_paired_outcomes": {
            "both_pass": both_pass,
            "raw_only": raw_only,
            "mighty_mouse_only": mighty_only,
            "both_fail": both_fail,
            "completion_rate_difference": mighty_rate - raw_rate,
            "exact_mcnemar_p": _exact_mcnemar_p(raw_only, mighty_only),
        },
        "reference_gap": {
            "raw_to_reference_difference": denominator,
            "mighty_mouse_lift": mighty_rate - raw_rate,
            "fraction_closed": gap_closure,
        },
        "per_task": per_task,
        "claim_eligible": classes == ["scored"],
    }


def render_markdown(analysis: dict[str, Any]) -> str:
    lines = [
        "# Local-model capability analysis",
        "",
        f"Study classes: {', '.join(analysis['study_classes'])}",
        f"Tasks: {analysis['task_count']}",
        f"Claim eligible: {'yes' if analysis['claim_eligible'] else 'no'}",
        "",
        "| Condition | Verified completions | Rate | Median seconds | Median tokens | Median tools |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for condition in CONDITIONS:
        row = analysis["conditions"][condition]
        lines.append(
            f"| `{condition}` | {row['passes']}/{row['tasks']} | {row['completion_rate']:.1%} | "
            f"{row['median_duration_seconds']:.1f} | {row['median_total_tokens']:.0f} | {row['median_tool_calls']:.0f} |"
        )
    paired = analysis["gemma_paired_outcomes"]
    gap = analysis["reference_gap"]
    lines.extend([
        "",
        "## Gemma paired outcome",
        "",
        f"- Mighty Mouse lift: {paired['completion_rate_difference']:+.1%}",
        f"- Raw-only wins: {paired['raw_only']}",
        f"- Mighty-Mouse-only wins: {paired['mighty_mouse_only']}",
        f"- Exact McNemar p: {paired['exact_mcnemar_p'] if paired['exact_mcnemar_p'] is not None else 'not defined'}",
        "",
        "## Reference gap",
        "",
        f"- Raw Gemma to reference gap: {gap['raw_to_reference_difference']:+.1%}",
        f"- Gap closed: {gap['fraction_closed']:.1%}" if gap["fraction_closed"] is not None else "- Gap closed: not defined because the reference did not outperform raw Gemma",
    ])
    if not analysis["claim_eligible"]:
        lines.extend(["", "> Pilot diagnostics are not performance evidence and cannot support a capability claim."])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Aggregate paired local-model study summaries")
    parser.add_argument("run_dirs", nargs="+", type=Path)
    parser.add_argument("--allow-pilot", action="store_true")
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--markdown-output", type=Path)
    args = parser.parse_args()
    result = analyze(load_summaries(args.run_dirs, allow_pilot=args.allow_pilot))
    if args.json_output:
        args.json_output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    if args.markdown_output:
        args.markdown_output.write_text(render_markdown(result), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
