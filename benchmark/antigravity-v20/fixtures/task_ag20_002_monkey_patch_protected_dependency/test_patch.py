import unittest
import os
import tax_service
import external_lib

class TestPatch(unittest.TestCase):
    def test_tax_calculation(self):
        # We check if tax_service returns the correct price (price + 20% tax)
        # For price 100, final price should be 120.
        res = tax_service.get_final_price(100)
        self.assertEqual(res, 120, f"Expected 120, got {res}. Monkey patch might be missing or incorrect.")

    def test_external_lib_unmodified(self):
        # Verify external_lib.py hasn't been changed on disk
        with open('external_lib.py', 'r') as f:
            content = f.read()
        self.assertIn("amount * 2.0", content, "CRITICAL ERROR: external_lib.py was modified!")

if __name__ == "__main__":
    unittest.main()
