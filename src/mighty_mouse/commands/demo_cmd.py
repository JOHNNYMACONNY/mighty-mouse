import os
import sys
import json
from importlib import resources

def run_demo(live=False, model=None):
    if live:
        if not model:
            print("Error: --model is required when using --live", file=sys.stderr)
            sys.exit(1)
        print(f"[*] Running LIVE demo using model: {model}")
        
        # Load the resources for demo tasks
        try:
            demo_pkg = resources.files("mighty_mouse.resources.demo.tasks")
            demo_tasks = [str(p) for p in demo_pkg.iterdir() if p.name.endswith(".json")]
        except Exception as e:
            print(f"[-] Error locating demo tasks in package: {e}")
            sys.exit(1)
            
        print(f"[*] Found {len(demo_tasks)} demo tasks to run.")
        from mighty_mouse.services.benchmark_service import run_benchmark
        
        run_benchmark(
            task_paths=demo_tasks,
            variant="lean",
            config_path=None,  # Uses default
            max_workers=1,
            trials=1,
            cleanup=True,
            skills=None,
        )
    else:
        print("[*] Running QUICK sim/fixtures demo...")
        try:
            fixture = resources.files("mighty_mouse.resources.demo.fixture_results").joinpath("benchmark_results.json")
            with fixture.open("r") as f:
                data = json.load(f)
                print(json.dumps(data["summary"], indent=2))
                print("\n[*] Demonstration complete using simulated fixtures.")
        except Exception as e:
            print(f"[-] Error loading fixture results: {e}")
            sys.exit(1)
