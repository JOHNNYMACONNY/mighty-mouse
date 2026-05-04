import unittest
import sys
import os

# Add the root of the task to sys.path so 'common', 'service_a', 'service_b' can be imported
sys.path.append(os.getcwd())

class TestCascade(unittest.TestCase):
    def test_id_type(self):
        from common.utils import get_next_id
        val = get_next_id()
        self.assertIsInstance(val, str, f"ID should be a string, got {type(val)}")
        self.assertTrue(val.startswith("ID_"), f"ID should start with ID_, got {val}")

    def test_service_a(self):
        from service_a.processor import process_item
        res = process_item("test")
        self.assertEqual(res["name"], "test")
        # After fix, sort_index should be a string like "ID_1_INDEX"
        self.assertIsInstance(res["sort_index"], str)

    def test_service_b(self):
        from service_b.registry import register_user, get_user
        uid = register_user("bobby")
        self.assertEqual(get_user(uid), "bobby")

if __name__ == "__main__":
    unittest.main()
