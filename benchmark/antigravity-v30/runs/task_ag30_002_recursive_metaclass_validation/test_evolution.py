import unittest
import evolution

class TestEvolution(unittest.TestCase):
    def test_missing_run_middle(self):
        try:
            class Middle(evolution.PluginBase):
                pass
            self.fail("Missing run method error not raised")
        except TypeError as e:
            self.assertEqual(str(e), "Missing run method")
    def test_missing_run_deep(self):
        class ValidMiddle(evolution.PluginBase):
            def run(self): pass
        try:
            class Leaf(ValidMiddle):
                pass
            self.fail("Missing run method error not raised")
        except TypeError as e:
            self.assertEqual(str(e), "Missing run method")

if __name__ == "__main__":
    unittest.main()
