import argparse
import json
import os
import sys
import time
import yaml
import shutil
import subprocess
from pathlib import Path

# Add src/mighty_mouse/orchestrator to path
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.join(_REPO_ROOT, "src", "mighty_mouse", "orchestrator"))
from ollama_client import OllamaClient
from response_parser import ResponseParser
from analyze_failure import get_category

def log(msg):
    print(msg, file=sys.stderr)

class DecomposedV2Runner:
    def __init__(self, config_path, task_path, workspace):
        self.workspace = Path(workspace).absolute()
        self.task_path = Path(task_path).absolute()
        
        with open(config_path, 'r') as f:
            self.cfg = yaml.safe_load(f)
        
        with open(self.task_path, 'r') as f:
            self.task_data = json.load(f)
            
        with open("configs/v2_prompts.yaml", 'r') as f:
            self.prompts = yaml.safe_load(f)
            
        self.client = OllamaClient(config=self.cfg)
        self.task_id = self.task_data.get('id', 'unknown')
        self.mighty_dir = self.workspace / ".mighty"
        self.snapshot_dir = self.mighty_dir / "snapshots"
        
        self.mighty_dir.mkdir(parents=True, exist_ok=True)
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)
        
        self.telemetry = {
            "task_id": self.task_id,
            "subtasks": [],
            "pass_1_latency": 0,
            "pass_1_tokens": 0,
            "total_latency": 0,
            "schema_valid": False,
            "files_touched": []
        }

    def validate_schema(self, subtasks):
        if not isinstance(subtasks, list):
            return False, "Not a list"
        if not subtasks:
            return False, "Empty subtask list"
        if len(subtasks) > 10:
            return False, f"Too many subtasks: {len(subtasks)} (max 10)"
            
        ids = set()
        expected_files = set(self.task_data.get("expected_files", []))
        covered_files = set()
        
        # Get existing files in workspace to detect "invented" files
        existing_files = set()
        if self.workspace.exists():
            for root, _, files in os.walk(self.workspace):
                if ".mighty" in root: continue
                for f in files:
                    rel = os.path.relpath(os.path.join(root, f), self.workspace)
                    existing_files.add(rel)
        
        allowed_files = expected_files | existing_files

        for st in subtasks:
            st_id = st.get("id", "unknown")
            if not all(k in st for k in ["id", "type", "files", "description", "dependencies"]):
                return False, f"Missing required fields in subtask {st_id}"
            
            if not st["files"]:
                 return False, f"Subtask {st_id} has empty files array"

            ids.add(st_id)
            
            # Path safety & Invented files
            for f in st["files"]:
                if ".." in f or f.startswith("/") or f.startswith(".mighty"):
                    return False, f"Unsafe file path: {f}"
                if f not in allowed_files:
                    return False, f"Invented file: {f} (not in expected_files or workspace)"
                # Coverage tracking
                covered_files.add(f)
        
        # Coverage check: Every expected file must be in at least one subtask
        missing_files = expected_files - covered_files
        if missing_files:
            return False, f"Missing expected files in planning: {list(missing_files)}"

        # Dependency check
        adj = {}
        for st in subtasks:
            st_id = st["id"]
            adj[st_id] = []
            for dep in st["dependencies"]:
                if dep not in ids:
                    return False, f"Dependency {dep} not found for {st_id}"
                adj[st_id].append(dep)
        
        # Cycle detection
        visited = set()
        path = set()
        def has_cycle(v):
            visited.add(v)
            path.add(v)
            for neighbor in adj.get(v, []):
                if neighbor not in visited:
                    if has_cycle(neighbor): return True
                elif neighbor in path:
                    return True
            path.remove(v)
            return False

        for node in ids:
            if node not in visited:
                if has_cycle(node):
                    return False, "Cyclic dependencies detected in subtasks"
        
        return True, None

    def take_snapshot(self, subtask_id):
        dest = self.snapshot_dir / subtask_id
        if dest.exists():
            shutil.rmtree(dest)
        dest.mkdir(parents=True, exist_ok=True)
        
        for item in self.workspace.iterdir():
            if item.name in [".mighty", "tmp", "__pycache__"]:
                continue
            target = dest / item.name
            if item.is_dir():
                shutil.copytree(item, target, symlinks=True)
            else:
                shutil.copy2(item, target)

    def verify_subtask(self, subtask):
        status = "success"
        errors = []
        env = dict(os.environ)
        env["PYTHONPATH"] = f"{str(self.workspace)}:{env.get('PYTHONPATH', '')}"
        
        for f in subtask["files"]:
            p = self.workspace / f
            if not p.exists():
                status = "fail"
                errors.append(f"Missing File: {f} was not created by the executor. Ensure you use the correct ```python:path/to/file.py format.")
                continue

            if f.endswith(".py"):
                try:
                    subprocess.check_output([sys.executable, "-m", "py_compile", str(p)], stderr=subprocess.STDOUT, env=env)
                except subprocess.CalledProcessError as e:
                    status = "fail"
                    errors.append(f"Syntax Error in {f}: {e.output.decode()}")
        return status, errors

    def log_response(self, task_id, subtask_id, attempt, response):
        log_dir = self.mighty_dir / "logs"
        log_dir.mkdir(exist_ok=True)
        fname = f"{task_id}_{subtask_id}_attempt_{attempt}.txt"
        with open(log_dir / fname, 'w') as f:
            f.write(response)

    def run(self):
        start_time = time.time()
        
        # Pass 1: Planning
        log(f"[*] Pass 1 (Planning) for {self.task_id}...")
        planner_prompt = self.prompts["planner"].replace("{{ task_json }}", json.dumps(self.task_data, indent=2))
        
        start_p1 = time.time()
        try:
            p1_res = self.client.generate_content("You are a modular planner.", planner_prompt)
            self.telemetry["pass_1_latency"] = round(time.time() - start_p1, 2)
            self.telemetry["pass_1_tokens"] = self.client.last_metadata.get("usage", {}).get("total_tokens", 0)
            
            self.log_response(self.task_id, "PLAN", 1, p1_res)
            
            import re
            json_match = re.search(r"\[.*\]", p1_res, re.DOTALL)
            if not json_match:
                return {"task_id": self.task_id, "status": "fail", "reason": "No JSON block found", "category": "PARSER"}
            
            subtasks = json.loads(json_match.group(0))
            valid, err = self.validate_schema(subtasks)
            if not valid:
                return {"task_id": self.task_id, "status": "fail", "reason": f"Schema Validation Failed: {err}", "category": "ADHERENCE"}
            
            self.telemetry["schema_valid"] = True
            with open(self.mighty_dir / "SUBTASKS.json", 'w') as f:
                json.dump(subtasks, f, indent=2)
                
        except Exception as e:
            return {"task_id": self.task_id, "status": "fail", "reason": f"Planner Error: {str(e)}", "category": "PARSER"}

        # Pass 2: Execution
        log(f"[*] Pass 2 (Execution) with {len(subtasks)} subtasks...")
        prior_state = "Initial state."
        all_touched = set()
        
        for i, st in enumerate(subtasks):
            st_id = st["id"]
            is_last = (i == len(subtasks) - 1)
            # Inject is_last for executor prompt targeting
            st["is_last"] = is_last
            
            log(f"  [>] Subtask {st_id}: {st['description']}")
            self.take_snapshot(st_id)
            
            executor_prompt = self.prompts["executor"] \
                .replace("{{ task_json }}", json.dumps(self.task_data, indent=2)) \
                .replace("{{ subtask_json }}", json.dumps(st, indent=2)) \
                .replace("{{ prior_state }}", prior_state)
            
            attempts = 0
            while attempts < 2:
                attempts += 1
                start_st = time.time()
                try:
                    st_res = self.client.generate_content("You are an atomic executor.", executor_prompt)
                    st_latency = time.time() - start_st
                    self.log_response(self.task_id, st_id, attempts, st_res)
                    
                    try:
                        output_paths = ResponseParser.parse_and_write(
                            st_res, 
                            workspace_root=str(self.workspace),
                            strict_code_hygiene=True  # Hardened for V2
                        )
                    except ValueError as ve:
                        if "XML leakage detected" in str(ve) and attempts < 2:
                            log(f"    [!] XML Leakage Detected in {st_id}. Retrying with hygiene correction...")
                            executor_prompt += f"\n\n[HYGIENE ERROR] {str(ve)}. Please repeat the file implementation WITHOUT including XML tags like </thought> or </act> inside the code blocks."
                            continue
                        raise # Re-raise if not leakage or out of attempts
                    
                    st_status, st_errors = self.verify_subtask(st)
                    
                    st_meta = {"id": st_id, "latency": round(st_latency, 2), "status": st_status, "errors": st_errors, "attempt": attempts, "files": output_paths}
                    if st_status == "success":
                        self.telemetry["subtasks"].append(st_meta)
                        all_touched.update([p for p in output_paths if not p.startswith(".mighty/")])
                        prior_state += f"\nSubtask {st_id} completed: {st['description']}"
                        break
                    else:
                        if attempts < 2:
                            log(f"    [!] Verification failed for {st_id}. Retrying...")
                            executor_prompt += f"\n\n[RETRY] Verification failed:\n" + "\n".join(st_errors)
                        else:
                            self.telemetry["subtasks"].append(st_meta)
                            return {"task_id": self.task_id, "status": "fail", "reason": f"Subtask {st_id} failed: {st_errors}", "category": "LOGIC"}
                except Exception as e:
                    return {"task_id": self.task_id, "status": "fail", "reason": f"Executor Error in {st_id}: {str(e)}", "category": "PARSER"}

        # Final Verification
        log(f"[*] Final Verification...")
        verify_script = os.path.join(os.getcwd(), "eval/run_benchmark.py")
        sandbox_wrapper = os.path.join(os.getcwd(), "eval/sandbox_wrapper.py")
        env = dict(os.environ)
        env["PYTHONPATH"] = f"{os.getcwd()}:{os.path.join(os.getcwd(), 'src/mighty_mouse/orchestrator')}:{os.path.join(os.getcwd(), 'eval')}:{str(self.workspace)}"
        
        ver_res = subprocess.run([sys.executable, sandbox_wrapper, verify_script, str(self.task_path)], capture_output=True, text=True, cwd=str(self.workspace), env=env)
        success = '"status": "success"' in ver_res.stdout
        self.telemetry["total_latency"] = round(time.time() - start_time, 2)
        self.telemetry["files_touched"] = list(all_touched)
        
        reason = None
        if not success:
            reason = ver_res.stdout
            if ver_res.stderr:
                reason += f"\nSTDERR:\n{ver_res.stderr}"
            if not reason.strip():
                reason = "Verification failed without output."

        return {
            "task_id": self.task_id,
            "status": "success" if success else "fail",
            "category": "SUCCESS" if success else "LOGIC",
            "reason": reason,
            "latency_seconds": self.telemetry.get("total_latency", 0),
            "telemetry": self.telemetry
        }

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config")
    parser.add_argument("--task")
    parser.add_argument("--workspace")
    args = parser.parse_args()
    runner = DecomposedV2Runner(args.config, args.task, args.workspace)
    print(json.dumps(runner.run()))
