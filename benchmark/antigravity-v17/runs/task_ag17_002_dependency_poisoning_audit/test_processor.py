import unittest
from processor import process_data

class TestProcessor(unittest.TestCase):
    def test_statelessness(self):
        # First call
        res1 = process_data("test")
        # Second call with same data should yield same result if stateless
        res2 = process_data("test")
        
        self.assertEqual(res1, res2, f"STATE LEAK DETECTED: {res1} != {res2}")

if __name__ == "__main__":
    unittest.main()
