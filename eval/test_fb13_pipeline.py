import unittest
import sys
import os
_EVAL_DIR = os.path.dirname(os.path.abspath(__file__))
if _EVAL_DIR not in sys.path: sys.path.append(_EVAL_DIR)

from tier_utils import load_tier_sequence, get_current_tier
from task_validator import validate_task_completeness, TaskValidationError

class TestFB13Pipeline(unittest.TestCase):
    def test_tier_sequence_loading(self):
        sequence = load_tier_sequence("eval/evaluation_config.json")
        self.assertIn("tier_1", sequence)
        self.assertIn("tier_8", sequence)
        self.assertEqual(sequence[-1], "tier_8")

    def test_task_validator_negative_controls(self):
        valid_task = {
            "id": "task_test_999",
            "title": "Test Dummy Task",
            "description": "Implement foo in foo.py",
            "expected_files": ["foo.py"],
            "test_script": '''import unittest, os
from foo import foo_func
class TestFoo(unittest.TestCase):
    def test_run(self):
        self.assertEqual(foo_func(), 42)
if __name__ == '__main__': unittest.main()
'''
        }
        ref_files = {"foo.py": "def foo_func(): return 42\n"}
        
        # Valid task with ref files passes
        self.assertTrue(validate_task_completeness(valid_task, reference_files=ref_files))

    def test_task_validator_rejects_empty_test(self):
        invalid_task = {
            "id": "task_bad",
            "title": "Bad Empty Task",
            "description": "Empty test task",
            "expected_files": ["foo.py"],
            "test_script": '''import unittest
class TestFoo(unittest.TestCase):
    def test_run(self): pass
if __name__ == '__main__': unittest.main()
'''
        }
        ref_files = {"foo.py": "pass"}
        with self.assertRaises(TaskValidationError):
            validate_task_completeness(invalid_task, reference_files=ref_files)

if __name__ == '__main__':
    unittest.main()
