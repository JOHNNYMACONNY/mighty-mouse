import unittest
from discounts import apply_premium_discount

class TestDiscounts(unittest.TestCase):
    def test_premium_small_order(self):
        # Base (0.05) * Multiplier (2.0) = 0.10 discount
        # $100 -> $90
        self.assertAlmostEqual(apply_premium_discount(100.0), 90.0)

    def test_premium_large_order(self):
        # Base (0.05) * Multiplier (2.0) = 0.10
        # + Legacy Bonus (0.05) = 0.15
        # $2000 -> $1700
        self.assertAlmostEqual(apply_premium_discount(2000.0), 1700.0)

if __name__ == "__main__":
    unittest.main()
