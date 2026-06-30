#!/usr/bin/env python3
"""Run the frozen corpus with one raw Ollama request per task.

This control intentionally imports no Mighty Mouse prompt, protocol, agent loop, or
retry machinery. The response parser is used only to materialize returned files so
the frozen task tests can execute.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request

from mighty_mouse.orchestrator.response_parser import ResponseParser


PROMPT_TEMPLATE = """You are completing a coding task.

Title: {title}
Task: {description}
Constraints: {constraints}
Required files: {expected_files}

Write the complete implementation. Return each required file as one fenced block
whose opening fence is exactly ```language:path. Do not omit the path.
"""


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def build_prompt(task: dict) -> str:
    return PROMPT_TEMPLATE.format(
        title=task.get("title", task["id"]),
        description=task["description"],
        constraints=json.dumps(task.get("constraints", {}), sort_keys=True),
        expected_files=", ".join(task.get("expected_files", [])),
    )


def request_generation(
    prompt: str,
    model: str,
    host: str,
    timeout_sec: int,
) -> tuple[str, dict]:
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.2, "num_predict": 4000, "num_ctx": 32768},
    }
    request = urllib.request.Request(
        host.rstrip("/") + "/api/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    started = time.monotonic()
    with urllib.request.urlopen(request, timeout=timeout_sec) as response:
        body = json.loads(response.read().decode("utf-8"))
    metadata = {
        "latency_seconds": round(time.monotonic() - started, 3),
        "prompt_tokens": body.get("prompt_eval_count", 0),
        "completion_tokens": body.get("eval_count", 0),
    }
    return body.get("response", ""), metadata


def ollama_provenance(host: str, model: str) -> dict:
    provenance = {"model": model, "version": "unknown", "model_digest": "unknown"}
    try:
        with urllib.request.urlopen(host.rstrip("/") + "/api/version", timeout=10) as response:
            provenance["version"] = json.loads(response.read().decode("utf-8")).get("version", "unknown")
        with urllib.request.urlopen(host.rstrip("/") + "/api/tags", timeout=10) as response:
            models = json.loads(response.read().decode("utf-8")).get("models", [])
        selected = next((item for item in models if item.get("name") == model), None)
        if selected:
            provenance["model_digest"] = selected.get("digest", "unknown")
    except Exception as exc:
        provenance["provenance_error"] = f"{type(exc).__name__}: {exc}"
    return provenance


def _run_frozen_test(task: dict, workspace: Path) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            [sys.executable, "-c", task["test_script"]],
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.returncode == 0, (result.stdout + result.stderr).strip()
    except subprocess.TimeoutExpired:
        return False, "Frozen task test timed out after 30 seconds."


def run_task(task_path: Path, workspace_root: Path, model: str, host: str, timeout_sec: int) -> dict:
    task = json.loads(task_path.read_text(encoding="utf-8"))
    workspace = workspace_root / task_path.stem
    if workspace.exists():
        shutil.rmtree(workspace)
    workspace.mkdir(parents=True, exist_ok=True)
    prompt = build_prompt(task)
    started_at = datetime.now(timezone.utc).isoformat()

    try:
        raw_response, metadata = request_generation(prompt, model, host, timeout_sec)
        extracted = ResponseParser.parse_and_write(raw_response, workspace_root=str(workspace))
        tests_passed, test_output = _run_frozen_test(task, workspace)
        missing = [name for name in task.get("expected_files", []) if not (workspace / name).is_file()]
        unexpected = sorted(
            str(path.relative_to(workspace))
            for path in workspace.rglob("*")
            if path.is_file()
            and "__pycache__" not in path.parts
            and path.suffix != ".pyc"
            and str(path.relative_to(workspace)) not in task.get("expected_files", [])
        )
        passed = tests_passed and not missing and not unexpected
        reason = "passed" if passed else "failed frozen tests or file-scope checks"
    except Exception as exc:
        raw_response = ""
        metadata = {"latency_seconds": 0.0, "prompt_tokens": 0, "completion_tokens": 0}
        extracted = []
        test_output = ""
        missing = list(task.get("expected_files", []))
        unexpected = []
        passed = False
        reason = f"generation error: {type(exc).__name__}: {exc}"

    return {
        "task_id": task["id"],
        "task_file": task_path.name,
        "task_sha256": _sha256_file(task_path),
        "prompt_sha256": _sha256_bytes(prompt.encode("utf-8")),
        "started_at": started_at,
        "model": model,
        "status": "success" if passed else "fail",
        "reason": reason,
        "latency_seconds": metadata["latency_seconds"],
        "prompt_tokens": metadata["prompt_tokens"],
        "completion_tokens": metadata["completion_tokens"],
        "extracted_files": extracted,
        "missing_files": missing,
        "unexpected_files": unexpected,
        "test_output": test_output,
        "raw_response": raw_response,
    }


def _write_json_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False, encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")
        temporary = handle.name
    os.replace(temporary, path)


def write_comparison(results: dict, evidence_results: Path, output_path: Path) -> None:
    validation_report = (evidence_results / "validation_report.md").read_text(encoding="utf-8")
    paired_rows = re.findall(
        r"^\| task_\S+ \| (success|fail) \([^|]+\) \| (success|fail) \([^|]+\) \|",
        validation_report,
        flags=re.MULTILINE,
    )
    if len(paired_rows) != 15:
        raise ValueError(f"Expected 15 paired rows in validation_report.md, found {len(paired_rows)}")
    bare_passes = sum(item["status"] == "success" for item in results["results"])
    harness_passes = sum(baseline == "success" for baseline, _ in paired_rows)
    lean_passes = sum(lean == "success" for _, lean in paired_rows)
    lines = [
        "# Bare vs Harness Baseline",
        "",
        "This report compares one raw model call per task with the recorded full-protocol baseline and Lean protocol runs. The bare condition has no Mighty Mouse prompt, checklist, adherence gate, or retry loop.",
        "",
        "| Condition | Passed | Notes |",
        "|---|---:|---|",
        f"| Bare Ollama control | {bare_passes}/{len(results['results'])} | One request; file materialization and frozen task tests only |",
        f"| Original harness baseline | {harness_passes}/{len(paired_rows)} | Recorded paired-validation baseline |",
        f"| Lean harness | {lean_passes}/{len(paired_rows)} | Recorded paired-validation Lean condition |",
        "",
        "## Interpretation",
        "",
    ]
    if bare_passes < harness_passes:
        lines.append(f"On this frozen corpus, the harness improved recorded task success by {harness_passes - bare_passes} tasks over the bare control.")
    else:
        lines.append("The frozen corpus did not show a success-rate advantage over the bare control. These permissive synthetic tasks have a ceiling effect, so the result does not support a generalized reliability-improvement claim.")
    lines.extend([
        "",
        "Latency comparisons across these artifacts are descriptive only because the runs occurred at different times and may not share identical runtime conditions.",
        "",
        "Every condition, including failures, is retained in `bare_baseline_results.json`.",
    ])
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the frozen 15-task bare Ollama control")
    parser.add_argument("--tasks-dir", default="data/evidence/tasks")
    parser.add_argument("--results", default="data/evidence/results/bare_baseline_results.json")
    parser.add_argument("--comparison", default="data/evidence/results/baseline_comparison.md")
    parser.add_argument("--workspace-dir")
    parser.add_argument("--model", default="gemma4:e4b")
    parser.add_argument("--host", default="http://localhost:11434")
    parser.add_argument("--timeout-sec", type=int, default=300)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    tasks_dir = Path(args.tasks_dir).resolve()
    task_paths = sorted(tasks_dir.glob("task_*.json"))
    if len(task_paths) != 15:
        parser.error(f"Expected exactly 15 frozen tasks, found {len(task_paths)} in {tasks_dir}")
    results_path = Path(args.results).resolve()
    workspace_root = Path(args.workspace_dir).resolve() if args.workspace_dir else Path(tempfile.mkdtemp(prefix="mighty_mouse_bare_"))
    existing: dict[str, dict] = {}
    existing_payload: dict | None = None
    if results_path.exists() and not args.force:
        existing_payload = json.loads(results_path.read_text(encoding="utf-8"))
        existing = {item["task_file"]: item for item in existing_payload.get("results", [])}
    runtime_provenance = ollama_provenance(args.host, args.model)
    metadata_update_needed = bool(existing_payload and "ollama" not in existing_payload)

    results = []
    for index, task_path in enumerate(task_paths, 1):
        if task_path.name in existing:
            result = existing[task_path.name]
            generated = False
            print(f"[{index:02}/15] {task_path.stem}: resumed {result['status']}", flush=True)
        else:
            result = run_task(task_path, workspace_root, args.model, args.host, args.timeout_sec)
            generated = True
            print(f"[{index:02}/15] {task_path.stem}: {result['status']} ({result['latency_seconds']}s)", flush=True)
        results.append(result)
        partial = {
            "schema_version": 1,
            "condition": "bare_ollama_single_call",
            "protocol_applied": False,
            "verification_retry_rounds": 0,
            "model": args.model,
            "ollama": runtime_provenance,
            "host": args.host,
            "prompt_template_sha256": _sha256_bytes(PROMPT_TEMPLATE.encode("utf-8")),
            "workspace_root": str(workspace_root),
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "summary": {"successes": sum(item["status"] == "success" for item in results), "total": len(results)},
            "results": results,
        }
        if generated or metadata_update_needed or args.force:
            _write_json_atomic(results_path, partial)
            metadata_update_needed = False

    write_comparison(partial, results_path.parent, Path(args.comparison).resolve())
    print(f"Results: {results_path}")
    print(f"Workspaces: {workspace_root}")
    return 0 if partial["summary"]["total"] == 15 else 1


if __name__ == "__main__":
    raise SystemExit(main())
