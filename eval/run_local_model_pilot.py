#!/usr/bin/env python3
"""Run one unscored three-condition local-model pilot task.

This coordinator is intentionally strict: it creates a new output directory,
copies the same source snapshot for every condition, randomizes condition order,
and records complete results. It never overwrites or resumes an existing run.
Scored study execution requires a separately frozen corpus and protocol commit.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import shutil
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

from mighty_mouse.experiments.local_agent import AgentBudget, OllamaChatClient, run_agent_condition


CONDITIONS = ("gemma_raw", "gemma_mighty_mouse", "reference_raw")


def _tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if not path.is_file() or ".git" in path.parts or "__pycache__" in path.parts:
            continue
        resolved = path.resolve()
        if resolved != root and root not in resolved.parents:
            continue
        relative = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        content = path.read_bytes()
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()


def _model_provenance(host: str, model: str) -> dict[str, Any]:
    with urllib.request.urlopen(f"{host.rstrip('/')}/api/tags", timeout=30) as response:
        models = json.loads(response.read().decode("utf-8")).get("models", [])
    selected = next((item for item in models if item.get("name") == model or item.get("model") == model), None)
    if not selected:
        raise ValueError(f"Ollama model is not installed or available: {model}")
    return {
        "name": model,
        "digest": selected.get("digest", "unknown"),
        "size": selected.get("size"),
        "details": selected.get("details", {}),
    }


def load_task(task_path: Path) -> tuple[dict[str, Any], Path]:
    task_path = task_path.resolve()
    task = json.loads(task_path.read_text(encoding="utf-8"))
    required = {"id", "description", "complexity", "workspace_template", "allowed_paths", "checks"}
    missing = sorted(required - task.keys())
    if missing:
        raise ValueError(f"Pilot task is missing required fields: {', '.join(missing)}")
    template = (task_path.parent / task["workspace_template"]).resolve()
    if not template.is_dir():
        raise ValueError(f"workspace_template is not a directory: {template}")
    if task["complexity"] not in {"low", "medium", "high"}:
        raise ValueError("complexity must be low, medium, or high")
    if not task["checks"]:
        raise ValueError("Pilot task must define at least one acceptance check")
    normalized_checks = {}
    for check_id, argv in task["checks"].items():
        if not isinstance(argv, list) or not argv or not all(isinstance(part, str) and part for part in argv):
            raise ValueError(f"Check {check_id} must be a non-empty argv array")
        normalized_checks[check_id] = [sys.executable if part == "{python}" else part for part in argv]
    task["checks"] = normalized_checks
    return task, template


def run_pilot(
    task_path: Path,
    output_dir: Path,
    *,
    gemma_model: str,
    reference_model: str,
    host: str,
    seed: int,
    budget: AgentBudget,
) -> dict[str, Any]:
    task, template = load_task(task_path)
    output_dir = output_dir.resolve()
    if output_dir.exists():
        raise FileExistsError(f"Refusing to overwrite existing pilot output: {output_dir}")
    if output_dir == template or template in output_dir.parents:
        raise ValueError("Output directory cannot be inside the workspace template")
    output_dir.mkdir(parents=True)
    (output_dir / "workspaces").mkdir()
    (output_dir / "results").mkdir()

    model_by_condition = {
        "gemma_raw": gemma_model,
        "gemma_mighty_mouse": gemma_model,
        "reference_raw": reference_model,
    }
    provenance = {
        model: _model_provenance(host, model)
        for model in sorted(set(model_by_condition.values()))
    }
    order = list(CONDITIONS)
    random.Random(f"{seed}:{task['id']}").shuffle(order)
    source_digest = _tree_digest(template)
    run_manifest = {
        "schema_version": 1,
        "study_class": "unscored_pilot",
        "task_id": task["id"],
        "task_source": str(task_path.resolve()),
        "source_digest": source_digest,
        "condition_order": order,
        "models": provenance,
        "seed": seed,
        "budget": budget.__dict__,
        "started_at_unix": time.time(),
    }
    (output_dir / "run_manifest.json").write_text(json.dumps(run_manifest, indent=2), encoding="utf-8")
    frozen_task = {**task, "workspace_template": str(template), "checks": task["checks"]}
    (output_dir / "task.json").write_text(json.dumps(frozen_task, indent=2), encoding="utf-8")

    results = {}
    for condition in order:
        workspace = output_dir / "workspaces" / condition
        shutil.copytree(
            template,
            workspace,
            symlinks=True,
            ignore=shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache", "node_modules"),
        )
        if _tree_digest(workspace) != source_digest:
            raise RuntimeError(f"Workspace copy mismatch before {condition}")
        result = run_agent_condition(
            OllamaChatClient(model_by_condition[condition], host=host, temperature=0.1, seed=seed),
            workspace,
            task,
            condition=condition,
            budget=budget,
        )
        results[condition] = result
        (output_dir / "results" / f"{condition}.json").write_text(json.dumps(result, indent=2), encoding="utf-8")

    summary = {
        "schema_version": 1,
        "study_class": "unscored_pilot",
        "task_id": task["id"],
        "condition_order": order,
        "results": {
            condition: {
                "model": result["model"],
                "passed": result["passed"],
                "turns": result["turns"],
                "tool_calls": result["tool_calls"],
                "duration_seconds": result["duration_seconds"],
                "total_tokens": result["usage"]["total_tokens"],
                "disallowed_changes": result["disallowed_changes"],
            }
            for condition, result in results.items()
        },
        "completed_at_unix": time.time(),
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Run an unscored three-condition local-model pilot task")
    parser.add_argument("--task", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--gemma-model", default="gemma4:e4b")
    parser.add_argument("--reference-model", required=True)
    parser.add_argument("--host", default="http://localhost:11434")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--max-turns", type=int, default=20)
    parser.add_argument("--max-tool-calls", type=int, default=40)
    parser.add_argument("--max-wall-seconds", type=int, default=900)
    parser.add_argument("--max-output-tokens", type=int, default=4_000)
    parser.add_argument("--context-tokens", type=int, default=32_768)
    args = parser.parse_args()
    summary = run_pilot(
        args.task,
        args.output_dir,
        gemma_model=args.gemma_model,
        reference_model=args.reference_model,
        host=args.host,
        seed=args.seed,
        budget=AgentBudget(
            max_turns=args.max_turns,
            max_tool_calls=args.max_tool_calls,
            max_wall_seconds=args.max_wall_seconds,
            max_output_tokens_per_turn=args.max_output_tokens,
            context_tokens=args.context_tokens,
        ),
    )
    print(json.dumps(summary, indent=2))
    return 0 if all(result["passed"] for result in summary["results"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
