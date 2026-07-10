#!/usr/bin/env python3
"""Run a frozen, held-out local-model capability corpus.

The corpus is intentionally supplied from a directory outside this repository:
task prompts and acceptance tests must not be published before the study is
complete.  A run directory is append-only and resumable at the condition level;
completed result files are never regenerated.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import shutil
import time
from copy import deepcopy
from pathlib import Path
from typing import Any

from eval.run_local_model_pilot import (
    CONDITIONS,
    _model_provenance,
    _run_baseline_checks,
    _tree_digest,
    _warm_model,
    load_task,
)
from mighty_mouse.experiments.local_agent import AgentBudget, OllamaChatClient, run_agent_condition


def _digest_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _copy_workspace(template: Path, destination: Path) -> None:
    if destination.exists():
        return
    shutil.copytree(
        template,
        destination,
        symlinks=True,
        ignore=shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache", "node_modules"),
    )


def _resolve_held_out_check_paths(task: dict[str, Any], template: Path) -> dict[str, Any]:
    """Anchor source-relative held-out checks before workspace copies are made.

    Public checks deliberately remain workspace-relative and agent-visible.  Only
    acceptance checks are rewritten, and only when a command argument names an
    existing path next to the private task definition.
    """
    resolved = deepcopy(task)
    checks = resolved.get("acceptance_checks", {})
    for check_id, argv in checks.items():
        anchored = []
        for argument in argv:
            candidate = (template / argument).resolve()
            if argument.startswith(("./", "../")) and candidate.exists():
                anchored.append(str(candidate))
            else:
                anchored.append(argument)
        checks[check_id] = anchored
    return resolved


def load_corpus(corpus_path: Path) -> tuple[dict[str, Any], list[Path]]:
    corpus_path = corpus_path.resolve()
    corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    required = {"schema_version", "study_class", "tasks"}
    missing = sorted(required - corpus.keys())
    if missing:
        raise ValueError(f"Corpus is missing required fields: {', '.join(missing)}")
    if corpus["study_class"] != "scored":
        raise ValueError("Corpus study_class must be scored")
    if not isinstance(corpus["tasks"], list) or len(corpus["tasks"]) < 30:
        raise ValueError("Scored corpus must contain at least 30 tasks")

    task_paths = []
    seen_ids = set()
    coding = agentic = 0
    complexity = {"low": 0, "medium": 0, "high": 0}
    repos = set()
    languages = set()
    for entry in corpus["tasks"]:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            raise ValueError("Each corpus task must provide a relative path")
        category = entry.get("category")
        if category not in {"coding", "agentic"}:
            raise ValueError("Each corpus task category must be coding or agentic")
        task_path = (corpus_path.parent / entry["path"]).resolve()
        if corpus_path.parent not in task_path.parents or not task_path.is_file():
            raise ValueError(f"Invalid corpus task path: {entry['path']}")
        task, _ = load_task(task_path)
        if task["id"] in seen_ids:
            raise ValueError(f"Duplicate task id in corpus: {task['id']}")
        seen_ids.add(task["id"])
        if task["complexity"] != entry.get("complexity"):
            raise ValueError(f"Corpus complexity does not match task: {task['id']}")
        if not entry.get("repository") or not entry.get("language"):
            raise ValueError(f"Corpus task needs repository and language metadata: {task['id']}")
        task_paths.append(task_path)
        coding += category == "coding"
        agentic += category == "agentic"
        complexity[task["complexity"]] += 1
        repos.add(entry["repository"])
        languages.add(entry["language"])
    if coding < 15 or agentic < 15:
        raise ValueError("Scored corpus requires at least 15 coding and 15 agentic tasks")
    if any(count < 10 for count in complexity.values()):
        raise ValueError("Scored corpus requires at least 10 tasks at each complexity")
    if len(repos) < 3 or len(languages) < 2:
        raise ValueError("Scored corpus requires at least three repositories and two languages")
    return corpus, task_paths


def _study_manifest(
    corpus_path: Path, corpus: dict[str, Any], *, gemma_model: str, reference_model: str,
    host: str, seed: int, budget: AgentBudget,
) -> dict[str, Any]:
    model_by_condition = {
        "gemma_raw": gemma_model,
        "gemma_mighty_mouse": gemma_model,
        "reference_raw": reference_model,
    }
    return {
        "schema_version": 1,
        "study_class": "scored",
        "corpus_digest": _digest_file(corpus_path),
        "corpus_schema_version": corpus["schema_version"],
        "task_count": len(corpus["tasks"]),
        "models": {model: _model_provenance(host, model) for model in sorted(set(model_by_condition.values()))},
        "model_by_condition": model_by_condition,
        "seed": seed,
        "budget": budget.__dict__,
    }


def _ensure_manifest(output_dir: Path, manifest: dict[str, Any]) -> None:
    path = output_dir / "study_manifest.json"
    if path.exists():
        prior = json.loads(path.read_text(encoding="utf-8"))
        if {key: prior.get(key) for key in manifest} != manifest:
            raise ValueError("Existing study manifest does not match this corpus, model, seed, or budget")
        return
    path.write_text(json.dumps({**manifest, "started_at_unix": time.time()}, indent=2), encoding="utf-8")


def run_study_task(
    task_path: Path, task_output: Path, *, manifest: dict[str, Any], host: str,
) -> dict[str, Any]:
    task, template = load_task(task_path)
    task_for_run = _resolve_held_out_check_paths(task, template)
    summary_path = task_output / "summary.json"
    if summary_path.exists():
        return json.loads(summary_path.read_text(encoding="utf-8"))
    task_output.mkdir(parents=True, exist_ok=True)
    (task_output / "results").mkdir(exist_ok=True)
    (task_output / "workspaces").mkdir(exist_ok=True)
    frozen = task_output / "task.json"
    if frozen.exists() and _digest_file(frozen) != _digest_file(task_path):
        raise ValueError(f"Task definition changed after execution began: {task['id']}")
    if not frozen.exists():
        shutil.copy2(task_path, frozen)

    baseline_workspace = task_output / "workspaces" / "baseline_validation"
    _copy_workspace(template, baseline_workspace)
    baseline_path = task_output / "baseline_checks.json"
    if baseline_path.exists():
        baseline_checks = json.loads(baseline_path.read_text(encoding="utf-8"))
    else:
        baseline_checks = _run_baseline_checks(task_for_run, baseline_workspace)
        baseline_path.write_text(json.dumps(baseline_checks, indent=2), encoding="utf-8")
    if baseline_checks and all(row["passed"] for row in baseline_checks.values()):
        raise ValueError(f"Task is already solved at baseline: {task['id']}")

    order = list(CONDITIONS)
    random.Random(f"{manifest['seed']}:{task['id']}").shuffle(order)
    task_manifest = {
        "schema_version": 1,
        "study_class": "scored",
        "task_id": task["id"],
        "task_digest": _digest_file(task_path),
        "source_digest": _tree_digest(template),
        "condition_order": order,
        "corpus_digest": manifest["corpus_digest"],
    }
    (task_output / "run_manifest.json").write_text(json.dumps(task_manifest, indent=2), encoding="utf-8")

    results: dict[str, dict[str, Any]] = {}
    for condition in order:
        result_path = task_output / "results" / f"{condition}.json"
        if result_path.exists():
            results[condition] = json.loads(result_path.read_text(encoding="utf-8"))
            continue
        workspace = task_output / "workspaces" / condition
        _copy_workspace(template, workspace)
        if _tree_digest(workspace) != task_manifest["source_digest"]:
            raise RuntimeError(f"Workspace copy mismatch before {task['id']}:{condition}")
        client = OllamaChatClient(manifest["model_by_condition"][condition], host=host, temperature=0.1, seed=manifest["seed"])
        warmup_path = task_output / "results" / f"{condition}.warmup.json"
        if not warmup_path.exists():
            warmup_path.write_text(json.dumps(_warm_model(client, AgentBudget(**manifest["budget"])), indent=2), encoding="utf-8")
        result = run_agent_condition(client, workspace, task_for_run, condition=condition, budget=AgentBudget(**manifest["budget"]))
        result_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
        results[condition] = result

    summary = {
        "schema_version": 1,
        "study_class": "scored",
        "task_id": task["id"],
        "condition_order": order,
        "baseline_checks": {check_id: row["passed"] for check_id, row in baseline_checks.items()},
        "results": {
            condition: {
                "model": result["model"], "passed": result["passed"], "turns": result["turns"],
                "tool_calls": result["tool_calls"], "duration_seconds": result["duration_seconds"],
                "total_tokens": result["usage"]["total_tokens"], "disallowed_changes": result["disallowed_changes"],
            }
            for condition, result in results.items()
        },
        "completed_at_unix": time.time(),
    }
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def run_study(
    corpus_path: Path, output_dir: Path, *, gemma_model: str, reference_model: str,
    host: str, seed: int, budget: AgentBudget,
) -> list[dict[str, Any]]:
    corpus, task_paths = load_corpus(corpus_path)
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = _study_manifest(corpus_path.resolve(), corpus, gemma_model=gemma_model, reference_model=reference_model, host=host, seed=seed, budget=budget)
    _ensure_manifest(output_dir, manifest)
    summaries = []
    for task_path in task_paths:
        task_id = json.loads(task_path.read_text(encoding="utf-8"))["id"]
        summaries.append(run_study_task(task_path, output_dir / "tasks" / task_id, manifest=manifest, host=host))
    return summaries


def main() -> int:
    parser = argparse.ArgumentParser(description="Run or resume a frozen held-out local-model study")
    parser.add_argument("--corpus", type=Path, required=True)
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
    summaries = run_study(args.corpus, args.output_dir, gemma_model=args.gemma_model, reference_model=args.reference_model, host=args.host, seed=args.seed, budget=AgentBudget(max_turns=args.max_turns, max_tool_calls=args.max_tool_calls, max_wall_seconds=args.max_wall_seconds, max_output_tokens_per_turn=args.max_output_tokens, context_tokens=args.context_tokens))
    print(json.dumps({"task_count": len(summaries), "completed": sum((args.output_dir / "tasks" / summary["task_id"] / "summary.json").is_file() for summary in summaries)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
