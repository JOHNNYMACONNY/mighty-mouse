import unittest
import os
import json
from pathlib import Path
import sys

# Add current dir to path
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(_REPO_ROOT)
from run_decomposed_v2 import DecomposedV2Runner

class TestSchemaValidation(unittest.TestCase):
    def setUp(self):
        self.config_path = "configs/mighty_mouse_v2_lean.yaml"
        self.task_path = "tasks/benchmark/task_040_legacy_decorator_circuitbreaker.json"
        self.workspace = "test_ws_schema"
        if not os.path.exists(self.workspace):
            os.makedirs(self.workspace)
        
        # Create a dummy task 040 json if not exists or just use existing
        self.runner = DecomposedV2Runner(self.config_path, self.task_path, self.workspace)
        # Task 040 expects ["legacy_decorator.py"]

    def tearDown(self):
        import shutil
        if os.path.exists(self.workspace):
            shutil.rmtree(self.workspace)

    def test_valid_schema(self):
        subtasks = [
            {
                "id": "ST1",
                "type": "modify",
                "files": ["legacy_decorator.py"],
                "description": "Implement decorator",
                "dependencies": []
            }
        ]
        valid, err = self.runner.validate_schema(subtasks)
        self.assertTrue(valid, f"Should be valid, got error: {err}")

    def test_empty_files_rejected(self):
        subtasks = [
            {
                "id": "ST1",
                "type": "modify",
                "files": [],
                "description": "Empty files",
                "dependencies": []
            }
        ]
        valid, err = self.runner.validate_schema(subtasks)
        self.assertFalse(valid)
        self.assertIn("empty files array", err)

    def test_missing_coverage_rejected(self):
        # Task 040 expects legacy_decorator.py
        subtasks = [
            {
                "id": "ST1",
                "type": "modify",
                "files": ["other.py"],
                "description": "Missing coverage",
                "dependencies": []
            }
        ]
        # We need to make sure 'other.py' is in workspace so it's not "invented"
        Path(self.workspace, "other.py").touch()
        # Re-init to pick up existing files
        self.runner = DecomposedV2Runner(self.config_path, self.task_path, self.workspace)
        
        valid, err = self.runner.validate_schema(subtasks)
        self.assertFalse(valid)
        self.assertIn("Missing expected files", err)

    def test_invented_files_rejected(self):
        subtasks = [
            {
                "id": "ST1",
                "type": "modify",
                "files": ["legacy_decorator.py", "ghost.py"],
                "description": "Invented file",
                "dependencies": []
            }
        ]
        valid, err = self.runner.validate_schema(subtasks)
        self.assertFalse(valid)
        self.assertIn("Invented file", err)

    def test_cyclic_dependencies_rejected(self):
        subtasks = [
            {
                "id": "ST1",
                "type": "modify",
                "files": ["legacy_decorator.py"],
                "description": "st1",
                "dependencies": ["ST2"]
            },
            {
                "id": "ST2",
                "type": "modify",
                "files": ["legacy_decorator.py"],
                "description": "st2",
                "dependencies": ["ST1"]
            }
        ]
        valid, err = self.runner.validate_schema(subtasks)
        self.assertFalse(valid)
        self.assertIn("Cyclic dependencies", err)

    def test_max_subtasks_enforced(self):
        subtasks = [{"id": f"ST{i}", "type": "modify", "files": ["legacy_decorator.py"], "description": "st", "dependencies": []} for i in range(11)]
        valid, err = self.runner.validate_schema(subtasks)
        self.assertFalse(valid)
        self.assertIn("Too many subtasks", err)

if __name__ == "__main__":
    unittest.main()
