import unittest
import multiprocessing
import orchestrator
import time

class TestBarrier(unittest.TestCase):
    def test_barrier_execution(self):
        manager = multiprocessing.Manager()
        results = manager.list()
        num_workers = 3
        barrier = multiprocessing.Barrier(num_workers)
        processes = []
        for i in range(num_workers):
            p = multiprocessing.Process(target=orchestrator.sync_work, args=(barrier, i, results))
            processes.append(p)
            p.start()
        for p in processes:
            p.join()
        setup_indices = [results.index(f"SETUP_DONE_{i}") for i in range(num_workers)]
        exec_indices = [results.index(f"EXEC_START_{i}") for i in range(num_workers)]
        self.assertLess(max(setup_indices), min(exec_indices), "Barrier failed")

if __name__ == "__main__":
    unittest.main()
