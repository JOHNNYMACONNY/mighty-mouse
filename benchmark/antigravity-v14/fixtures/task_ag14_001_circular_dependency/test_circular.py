import unittest
import os
import sys

# Add current dir to sys.path to simulate the environment
sys.path.append(os.path.dirname(__file__))

class TestCircular(unittest.TestCase):
    def test_logic(self):
        try:
            from module_a import calculate_total
            from module_b import display_all
            
            self.assertEqual(calculate_total(), "A + Value B")
            self.assertEqual(display_all(), "B + Value A")
        except ImportError as e:
            self.fail(f"Import failed: {e}. The circular dependency is likely still present or the refactor is broken.")

    def test_shared_logic(self):
        # After refactor, shared_logic should be in base.py
        try:
            from base import shared_logic
            self.assertEqual(shared_logic(5), 10)
        except ImportError:
            self.fail("base.py with shared_logic not found.")

if __name__ == "__main__":
    unittest.main()
