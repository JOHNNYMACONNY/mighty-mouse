import os
import sys
import json
import tempfile
from importlib import resources

def _copy_resource_tree(source, destination):
    os.makedirs(destination, exist_ok=True)
    for item in source.iterdir():
        target = os.path.join(destination, item.name)
        if item.is_dir():
            _copy_resource_tree(item, target)
        else:
            with item.open("rb") as input_file, open(target, "wb") as output_file:
                output_file.write(input_file.read())


def _prepare_live_resources(model, output_dir):
    import yaml

    config_root = os.path.join(output_dir, "config")
    tasks_root = os.path.join(output_dir, "input_tasks")
    _copy_resource_tree(resources.files("mighty_mouse.resources.configs"), config_root)
    _copy_resource_tree(resources.files("mighty_mouse.resources.demo.tasks"), tasks_root)

    base_config_path = os.path.join(config_root, "mighty_mouse_v2_lean.yaml")
    with open(base_config_path, "r") as config_file:
        config = yaml.safe_load(config_file)

    config["model"] = model
    config["system_prompt_path"] = os.path.abspath(
        os.path.join(config_root, config["system_prompt_path"])
    )
    config["prompt_segments"] = [
        os.path.abspath(os.path.join(config_root, segment))
        for segment in config.get("prompt_segments", [])
    ]

    live_config_path = os.path.join(config_root, "live_config.yaml")
    with open(live_config_path, "w") as config_file:
        yaml.safe_dump(config, config_file, sort_keys=False)

    task_paths = sorted(
        os.path.join(tasks_root, name)
        for name in os.listdir(tasks_root)
        if name.endswith(".json")
    )
    return live_config_path, task_paths


def run_demo(live=False, model=None, output_dir=None):
    if live:
        if not model:
            print("Error: --model is required when using --live", file=sys.stderr)
            sys.exit(1)
        print(f"[*] Running LIVE demo using model: {model}")
        
        output_root = os.path.abspath(output_dir or tempfile.mkdtemp(prefix="mighty_mouse_demo_"))
        try:
            temp_config_path, demo_tasks = _prepare_live_resources(model, output_root)
        except Exception as e:
            print(f"[-] Error preparing packaged demo resources: {e}")
            sys.exit(1)

        print(f"[*] Found {len(demo_tasks)} demo tasks to run.")
        from mighty_mouse.services.benchmark_service import main as service_run_benchmark
        results = service_run_benchmark(
            tasks_list=demo_tasks,
            variant="lean",
            config_path=temp_config_path,
            max_workers=1,
            trials=1,
            output_dir=output_root,
        )
        if results and "summary" in results:
            print(f"\n[*] LIVE Demonstration complete. Summary:\n{json.dumps(results['summary'], indent=2)}")
            print(f"[*] Results saved under: {results['output_dir']}")
            success, total = results["summary"]["success_rate"].split("/", 1)
            if success != total:
                sys.exit(1)
        else:
            print("\n[-] LIVE demonstration did not return a summary.", file=sys.stderr)
            sys.exit(1)
    else:
        print("[*] Running QUICK sim/fixtures demo...")
        try:
            fixture = resources.files("mighty_mouse.resources.demo.fixture_results").joinpath("benchmark_results.json")
            with fixture.open("r") as f:
                data = json.load(f)
                print(json.dumps(data["summary"], indent=2))
                print("\n[*] Recorded fixture replay complete; no model was executed.")
        except Exception as e:
            print(f"[-] Error loading fixture results: {e}")
            sys.exit(1)
