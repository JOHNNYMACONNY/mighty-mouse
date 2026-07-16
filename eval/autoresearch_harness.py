import argparse
import sys
import os
import json
import tempfile
import shutil
import subprocess
import traceback
from pathlib import Path

from mighty_mouse.experiments.local_agent import OllamaChatClient
from mighty_mouse.orchestrator.response_parser import ResponseParser
from eval.run_local_model_pilot import load_task


def run_task(task_path: Path, model: str, host: str) -> bool:
    print(f"--- Running task: {task_path.parent.name} ({task_path.name}) ---", file=sys.stderr)
    try:
        task, template = load_task(task_path)
    except Exception as e:
        print(f"Failed to load task {task_path}: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return False

    complexity = task.get("complexity", "low")
    protocol_path = Path("src/mighty_mouse/protocols/v9.1") / f"{complexity}.md"
    if not protocol_path.exists():
        print(f"Protocol file not found: {protocol_path}", file=sys.stderr)
        return False

    try:
        protocol_content = protocol_path.read_text(encoding="utf-8")
    except Exception as e:
        print(f"Failed to read protocol {protocol_path}: {e}", file=sys.stderr)
        return False

    file_context = ""
    for allowed in task.get("allowed_paths", []):
        file_path = template / allowed
        if file_path.is_file():
            try:
                content = file_path.read_text(encoding="utf-8")
                file_context += f"\n\nExisting File: {allowed}\n```python\n{content}\n```"
            except Exception as e:
                print(f"Failed to read file context for {allowed}: {e}", file=sys.stderr)

    prompt = f"{protocol_content}\n\nTask:\n{task['description']}{file_context}"

    with tempfile.TemporaryDirectory() as temp_dir:
        # Copy workspace files from template to temp_dir
        try:
            for item in os.listdir(template):
                s = os.path.join(template, item)
                d = os.path.join(temp_dir, item)
                if os.path.isdir(s):
                    shutil.copytree(s, d, symlinks=True)
                else:
                    shutil.copy(s, d)
        except Exception as e:
            print(f"Failed to copy workspace template for {task['id']}: {e}", file=sys.stderr)
            return False

        # Query Ollama
        client = OllamaChatClient(model=model, host=host, temperature=0.1, seed=7)
        messages = [{"role": "user", "content": prompt}]
        try:
            print(f"Querying model {model} at {host}...", file=sys.stderr)
            response, metrics = client.chat(
                messages=messages,
                tools=[],
                timeout_seconds=300,
                output_tokens=4000,
                context_tokens=32768,
            )
            raw_text = response.get("content", "")
        except Exception as e:
            print(f"Ollama call failed for {task['id']}: {e}", file=sys.stderr)
            return False

        # Parse response and apply edits in-place to temp_dir
        try:
            ResponseParser.parse_and_write(raw_text, workspace_root=temp_dir)
        except Exception as e:
            print(f"Response parser failed for {task['id']}: {e}", file=sys.stderr)
            return False

        # Run acceptance checks
        test_cmd = task.get("checks", {}).get("tests")
        if not test_cmd:
            test_cmd = task.get("acceptance_checks", {}).get("tests")
        if not test_cmd:
            print(f"No test check command configured for {task['id']}", file=sys.stderr)
            return False

        try:
            env = os.environ.copy()
            # Ensure workspace path is first in PYTHONPATH so code imports correctly
            env["PYTHONPATH"] = f"{temp_dir}:{env.get('PYTHONPATH', '')}"
            timeout = task.get("check_timeout_seconds", 30)

            print(f"Running tests: {test_cmd}", file=sys.stderr)
            result = subprocess.run(
                test_cmd,
                cwd=temp_dir,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
            )
            if result.returncode == 0:
                print(f"Result: PASS", file=sys.stderr)
                return True
            else:
                print(f"Result: FAIL (exit code {result.returncode})", file=sys.stderr)
                print(f"--- STDOUT ---\n{result.stdout}", file=sys.stderr)
                print(f"--- STDERR ---\n{result.stderr}", file=sys.stderr)
                return False
        except subprocess.TimeoutExpired:
            print(f"Result: FAIL (timeout after {timeout}s)", file=sys.stderr)
            return False
        except Exception as e:
            print(f"Result: FAIL (exception during test run: {e})", file=sys.stderr)
            return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Autoresearch evaluation harness bridge")
    parser.add_argument("--tasks-dir", type=Path, default=Path("eval/local_model_pilot"))
    parser.add_argument("--model", default="gemma4:e4b")
    parser.add_argument("--host", default="http://localhost:11434")
    parser.add_argument("--fast", action="store_true", help="Run only the 3 original pilot tasks (*-1)")
    args = parser.parse_args()

    tasks_dir = args.tasks_dir.resolve()
    if not tasks_dir.is_dir():
        print(f"Tasks directory not found: {tasks_dir}", file=sys.stderr)
        return 1

    # Find task.json in all subdirectories
    task_files = sorted(tasks_dir.glob("**/task.json"))
    if not task_files:
        print(f"No tasks found in {tasks_dir}", file=sys.stderr)
        return 1

    # Filter by fast mode
    if args.fast:
        # Keep only low-1, medium-1, high-1
        task_files = [t for t in task_files if t.parent.name in ("low-1", "medium-1", "high-1")]

    print(f"Found {len(task_files)} tasks to run.", file=sys.stderr)

    passed_count = 0
    for task_file in task_files:
        if run_task(task_file, args.model, args.host):
            passed_count += 1

    pass_rate = passed_count / len(task_files) if task_files else 0.0
    print(f"pass_rate: {pass_rate:.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
