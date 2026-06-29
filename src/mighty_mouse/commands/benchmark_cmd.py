import os
import sys

def run_benchmark(generate=False, tier="tier_1"):
    if generate:
        print("[-] Full 1,600-task corpus generation is not implemented in this version.")
        sys.exit(1)
    
    print(f"[*] Running benchmarks for {tier}...")
    from mighty_mouse.services.benchmark_service import run_benchmark as service_run_benchmark
    
    # Normally we would fetch the list of tasks for the tier
    # For now, we expect tasks/benchmark to be populated or we use a subset.
    tasks_dir = "tasks/benchmark"
    if not os.path.exists(tasks_dir):
        print(f"[-] {tasks_dir} not found. Ensure you are running from the project root or tasks exist.")
        sys.exit(1)
        
    tasks = [os.path.join(tasks_dir, f) for f in os.listdir(tasks_dir) if f.endswith(".json")]
    
    service_run_benchmark(
        task_paths=tasks,
        variant="lean",
        config_path=None,
        max_workers=4,
        trials=2,
        cleanup=True,
    )
