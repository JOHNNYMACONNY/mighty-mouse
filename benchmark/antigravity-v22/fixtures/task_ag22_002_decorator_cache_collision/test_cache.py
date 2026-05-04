import unittest
from cache_util import memoize

class Service:
    def __init__(self, multiplier):
        self.multiplier = multiplier
        self.call_count = 0

    @memoize
    def get_val(self, x):
        self.call_count += 1
        return x * self.multiplier

class TestCache(unittest.TestCase):
    def test_cache_collision(self):
        s1 = Service(10)
        s2 = Service(20)
        res1 = s1.get_val(10)
        self.assertEqual(res1, 100)
        res2 = s2.get_val(10)
        self.assertEqual(res2, 200, "DATA LEAKAGE: s2 returned cached value from s1")
        self.assertEqual(s1.call_count, 1)
        self.assertEqual(s2.call_count, 1)

if __name__ == "__main__":
    unittest.main()
