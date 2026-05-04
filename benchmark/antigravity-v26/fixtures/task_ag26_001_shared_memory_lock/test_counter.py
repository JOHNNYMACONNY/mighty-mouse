import unittest
import multiprocessing
import counter

def worker(shared_cnt):
    for _ in range(100):
        shared_cnt.increment()

class TestCounter(unittest.TestCase):
    def test_concurrent_increments(self):
        shared_cnt = counter.SharedCounter()
        processes = []
        for _ in range(10):
            p = multiprocessing.Process(target=worker, args=(shared_cnt,))
            processes.append(p)
            p.start()
        for p in processes:
            p.join()
        self.assertEqual(shared_cnt.val.value, 1000, f"Counter value {shared_cnt.val.value} != 1000")

if __name__ == "__main__":
    unittest.main()
