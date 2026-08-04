"""Legacy benchmark-result adapter over the canonical Verifier Seam."""

from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
import subprocess
import sys

_SERVICES_DIR = Path(__file__).resolve().parents[1]
_REPO_ROOT = _SERVICES_DIR.parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from mighty_mouse.verifier import verify


def _get_json_data(path: str | Path, default_val):
    target = Path(path)
    if not target.exists():
        return default_val
    try:
        return json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default_val


def _save_json_data(path: str | Path, data) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, indent=2), encoding="utf-8")


def update_checkpoint(task_id: str) -> None:
    checkpoint_path = Path("logs/session_checkpoint.json")
    data = _get_json_data(checkpoint_path, {"completed_tasks": []})
    if task_id not in data["completed_tasks"]:
        data["completed_tasks"].append(task_id)
    try:
        data["git_hash"] = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        pass
    _save_json_data(checkpoint_path, data)


def verify_task(task_config: dict, workspace: str | None = None) -> dict:
    """Run a task fixture through ``mighty_mouse.verifier.verify``."""
    target_workspace = os.path.abspath(workspace or os.getcwd())
    result = verify(target_workspace, task_config=task_config)
    checks = {check.name: check for check in result.checks}
    adherence = checks.get("task-adherence")
    scope = checks.get("task-scope")
    task_tests = checks.get("task-tests")
    status = "success" if result.passed else "fail"
    update_checkpoint(str(task_config["id"]))

    if scope is not None and not scope.passed:
        reason = scope.output
    elif task_tests is not None and not task_tests.passed:
        reason = "Tests failed"
    elif adherence is not None and not adherence.passed:
        reason = "Adherence failed"
    else:
        reason = "All checks passed" if result.passed else result.summary
    legacy = {
        "task_id": task_config["id"],
        "status": status,
        "adherence": "PASS" if adherence is None or adherence.passed else "FAIL",
        "scope": "PASS" if scope is None or scope.passed else "FAIL",
        "reason": reason,
        "adherence_logs": "" if adherence is None else adherence.output,
        "test_logs": "" if task_tests is None else task_tests.output,
        "timestamp": datetime.now().isoformat(),
    }
    if scope is not None:
        legacy.update(scope.details)
    return legacy


def main() -> None:
    if len(sys.argv) <= 1:
        return
    task_path = Path(sys.argv[1])
    task_config = json.loads(task_path.read_text(encoding="utf-8"))
    result = verify_task(task_config)
    history_path = Path("logs/benchmark_results.json")
    data = _get_json_data(history_path, {"results": []})
    history_list = data if isinstance(data, list) else data.get("results", [])
    existing_record = next((item for item in history_list if item.get("task_id") == result["task_id"]), {})
    history_list = [item for item in history_list if item.get("task_id") != result["task_id"]]
    history_list.append({**existing_record, **result})
    if isinstance(data, dict):
        data["results"] = history_list
        if "summary" in data:
            success_count = sum(item.get("status") == "success" for item in history_list)
            data["summary"]["success_rate"] = f"{success_count}/{len(history_list)}"
            data["summary"]["timestamp"] = datetime.now().isoformat()
            data["summary"]["updated_by"] = "run_benchmark"
        _save_json_data(history_path, data)
    else:
        _save_json_data(history_path, history_list)
    print(json.dumps(result, indent=2))
    print(f"Task {result['task_id']} {result['status']}: {result['reason']}")


if __name__ == "__main__":
    main()
