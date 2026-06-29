import os
import sys
import json
import tempfile
from importlib import resources

def _copy_packaged_tasks(destination):
    os.makedirs(destination, exist_ok=True)
    task_package = resources.files("mighty_mouse.resources.demo.tasks")
    task_paths = []
    for item in task_package.iterdir():
        if not item.name.endswith(".json"):
            continue
        target = os.path.join(destination, item.name)
        with item.open("rb") as source, open(target, "wb") as output:
            output.write(source.read())
        task_paths.append(target)
    return sorted(task_paths)


def run_benchmark(tasks_dir=None, output_dir=None):
    print("[*] Running benchmarks...")
    from mighty_mouse.services.benchmark_service import main as service_run_benchmark

    output_root = os.path.abspath(output_dir or tempfile.mkdtemp(prefix="mighty_mouse_"))
    if tasks_dir:
        if not os.path.exists(tasks_dir):
            print(f"[-] {tasks_dir} not found.")
            sys.exit(1)
        print(f"[*] Using user-supplied tasks from: {os.path.abspath(tasks_dir)}")
        tasks = sorted(
            os.path.abspath(os.path.join(tasks_dir, name))
            for name in os.listdir(tasks_dir)
            if name.endswith(".json")
        )
    else:
        print("[*] Using the 5 packaged demo tasks.")
        try:
            tasks = _copy_packaged_tasks(os.path.join(output_root, "input_tasks"))
        except Exception as e:
            print(f"[-] Error locating demo tasks in package: {e}")
            sys.exit(1)

    if not tasks:
        print("[-] No tasks found to run.")
        sys.exit(1)
        
    results = service_run_benchmark(
        tasks_list=tasks,
        variant="lean",
        config_path=None,
        max_workers=1,
        trials=1,
        output_dir=output_root,
    )
    if results and "summary" in results:
        print(f"\n[*] Benchmark complete. Summary:\n{json.dumps(results['summary'], indent=2)}")
        print(f"[*] Results saved under: {results['output_dir']}")
        success, total = results["summary"]["success_rate"].split("/", 1)
        if success != total:
            sys.exit(1)
    else:
        print("[-] Benchmark did not return a summary.", file=sys.stderr)
        sys.exit(1)
