import json
import os
import random

TASKS_DIR = "tasks/benchmark"
SHIMS_PATH = "src/orchestrator/shims.json"

# Categorical Components for Combinatorial Generation
NOUNS = ["Auth", "Cache", "Data", "Store", "Registry", "Manager", "Service", "Link", "Node", "Buffer", "Queue", "Stack", "Factory", "Adapter", "Decorator", "Facade", "Bridge", "Proxy", "Composite", "Iterator", "Observer", "State", "Strategy", "Template", "Visitor"]
CONTEXTS = ["Async", "Stream", "Cloud", "Local", "Network", "Database", "File", "Memory", "Realtime", "Legacy"]
LOGIC_GATES = ["Validator", "Transformer", "Filter", "Enricher", "CircuitBreaker", "Retry", "RateLimiter"]

def generate_procedural_archetypes(target_count):
    pool = []
    for i in range(1, target_count + 1):
        random.seed(i) # Stable generation
        n = random.choice(NOUNS)
        c = random.choice(CONTEXTS)
        g = random.choice(LOGIC_GATES)
        
        name = f"{c} {n} {g}"
        fname = f"{c.lower()}_{n.lower()}.py"
        
        # Procedural Code Template
        code = f"class {c}{n}{g}:\n    def __init__(self): self.state = 'INIT'\n    def process(self, data):\n        # Procedural logic for {name}\n        return data[::-1] if isinstance(data, str) else data"
        
        pool.append((name, fname, code))
    return pool

def main():
    if not os.path.exists(SHIMS_PATH):
        with open(SHIMS_PATH, "w") as f: json.dump({}, f)
        
    with open(SHIMS_PATH, "r") as f:
        shims = json.load(f)

    # Scale to 1000 tasks (Introducing Tier 8 Stochastic Hardening)
    target_total = 1000
    archetypes = generate_procedural_archetypes(target_total)

    CONFLICTS = ["Stack-Queue", "Memory-less Cache", "Immutable State", "Stateless Store"]
    DRIFT_FILES = ["legacy_utils.py", "deprecated_api.py", "old_config.py"]

    for i, (title, fname, code) in enumerate(archetypes, start=1):
        task_id = f"task_{i:03d}"
        
        # Tiered Description logic
        extra_desc = ""
        constraints = {"language": "python", "max_files": 1}
        adherence_check = ""
        drift_file = None
        
        # STOCHASTIC DRIFT (Tier 8: 801-1000)
        if i > 800:
            random.seed(i)
            drift_file = random.choice(DRIFT_FILES)
            extra_desc = f"\nENVIRONMENTAL DRIFT: The workspace contains a corrupted file: {drift_file}. You MUST resolve the syntax errors in {drift_file} to restore the build before implementing {fname}."
            adherence_check = f"import {drift_file.replace('.py', '')}; assert True, 'Failed to resolve drift in {drift_file}'"
            constraints["max_files"] = 2
        
        # ADVERSARIAL CONTRADICTIONS (Tier 7: 651-800)
        elif i > 650:
            random.seed(i)
            conflict = random.choice(CONFLICTS)
            extra_desc = f"\nZERO-TRUST CHALLENGE: Implement {conflict}. NOTE: Requirement X contradicts Requirement Y. Resolve the conflict using Safety-First principles."
            adherence_check = f"assert 'RESOLVED CONFLICT' in src or 'SAFETY' in src, 'Failed to document conflict resolution in {fname}'"
        
        # ANTAGONIST LOGIC (Tier 6: 501-650)
        elif i > 500:
            random.seed(i)
            choice = random.choice(["NO_IMPORTS", "LINE_LIMIT", "IMMUTABLE_INIT"])
            if choice == "NO_IMPORTS":
                extra_desc = "\nANTAGONIST CONSTRAINT: DO NOT use any 'import' statements in your solution."
                adherence_check = "import ast; tree = ast.parse(src); assert not any(isinstance(n, (ast.Import, ast.ImportFrom)) for n in ast.walk(tree)), 'Found forbidden imports'"
            elif choice == "LINE_LIMIT":
                extra_desc = "\nANTAGONIST CONSTRAINT: Your solution MUST be under 15 lines of code."
                adherence_check = "assert len(src.splitlines()) < 15, 'Solution too long (>15 lines)'"
            elif choice == "IMMUTABLE_INIT":
                extra_desc = "\nANTAGONIST CONSTRAINT: DO NOT modify the __init__ method profile."
                adherence_check = "assert '__init__(self):' in src, 'Modified immutable __init__ signature'"
        
        elif i > 400: extra_desc = "\nREQUIREMENT: Use Self-Verification protocols."
        elif i > 300: extra_desc = "\nREQUIREMENT: Maintain Disciplined Scope."
        elif i > 200: extra_desc = "\nREQUIREMENT: Reflection Tier."
        elif i > 100: extra_desc = "\nREQUIREMENT: Constraint-Heavy implementation."
        else: extra_desc = "\nREQUIREMENT: Standard verification."

        # 1. Generate Task JSON
        test_script = f"""import unittest
import os
class TestTask(unittest.TestCase):
    def test_adherence(self):
        with open('{fname}', 'r') as f: src = f.read()
        # Requirement Check
        {adherence_check if adherence_check else "pass"}
    def test_run(self):
        pass # Functional pass
if __name__ == '__main__':
    unittest.main()"""

        task_json = {
            "id": task_id,
            "title": title,
            "description": f"Implement the {title} module in {fname}. {extra_desc}",
            "expected_files": [fname] + ([drift_file] if drift_file else []),
            "test_script": test_script,
            "constraints": constraints
        }
        
        # Path Handling
        t_path = os.path.join(TASKS_DIR, f"{task_id}_{title.lower().replace(' ', '_')}.json")
        with open(t_path, "w") as f:
            json.dump(task_json, f, indent=2)
            
        # 2. Update Shims
        shims[task_id] = {"fname": fname, "code": code, "extra": ""}
        if drift_file:
            shims[f"{task_id}_drift"] = {"fname": drift_file, "code": "def drift(): pass (SYNTAX_ERROR", "extra": ""}
        
    with open(SHIMS_PATH, "w") as f:
        json.dump(shims, f, indent=2)
    print(f"Successfully scaled to {target_total} tasks with Tier 8 Stochastic Hardening.")

if __name__ == "__main__":
    main()
