import unittest
import multiprocessing
import cache_manager

class TestCache(unittest.TestCase):
    def test_eviction(self):
        manager = multiprocessing.Manager()
        d = manager.dict()
        o = manager.list()
        l = manager.Lock()
        cache = cache_manager.LimitedSharedDict(d, o, l, 2)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("c", 3)
        self.assertNotIn("a", d)
        self.assertIn("b", d)
        self.assertIn("c", d)
        self.assertEqual(len(d), 2)

if __name__ == "__main__":
    unittest.main()
