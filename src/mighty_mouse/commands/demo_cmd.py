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
        from mighty_mouse.services.benchmark_service import main as service_run_benchmark
        import tempfile
        import yaml
        
        # Load the base config from resources
        try:
            base_cfg_path = str(resources.files("mighty_mouse.resources.configs").joinpath("mighty_mouse_v2_lean.yaml"))
            with open(base_cfg_path, "r") as f:
                base_cfg = yaml.safe_load(f)
        except Exception as e:
            print(f"[-] Error loading base config: {e}")
            sys.exit(1)
            
        base_cfg["model"] = model
        
        # Create temp config
        fd, temp_config_path = tempfile.mkstemp(suffix=".yaml")
        with os.fdopen(fd, "w") as f:
            yaml.dump(base_cfg, f)
            
        try:
            results = service_run_benchmark(
                tasks_list=demo_tasks,
                variant="lean",
                config_path=temp_config_path,
                max_workers=1,
                trials=1,
            )
            if results and "summary" in results:
                print(f"\n[*] LIVE Demonstration complete. Summary:\n{json.dumps(results['summary'], indent=2)}")
            else:
                print("\n[*] LIVE Demonstration complete, but no summary was returned.")
        finally:
            if os.path.exists(temp_config_path):
                os.remove(temp_config_path)
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
