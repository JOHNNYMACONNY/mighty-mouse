import os
import sys
import json

def run_benchmark(tier="tier_1", tasks_dir=None):
    print(f"[*] Running benchmarks...")
    from mighty_mouse.services.benchmark_service import main as service_run_benchmark
    from importlib import resources
    
    tasks = []
    if tasks_dir:
        if not os.path.exists(tasks_dir):
            print(f"[-] {tasks_dir} not found.")
            sys.exit(1)
        tasks = [os.path.join(tasks_dir, f) for f in os.listdir(tasks_dir) if f.endswith(".json")]
    else:
        print(f"[*] Loading packaged demo tasks for {tier}...")
        try:
            demo_pkg = resources.files("mighty_mouse.resources.demo.tasks")
            tasks = [str(p) for p in demo_pkg.iterdir() if p.name.endswith(".json")]
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
        max_workers=4,
        trials=2,
    )
    if results and "summary" in results:
        print(f"\n[*] Benchmark complete. Summary:\n{json.dumps(results['summary'], indent=2)}")
