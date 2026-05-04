# Task: Shared Memory Lock (task_ag26_001)

## Context
Our multi-process metrics system is under-counting because multiple processes are updating the shared counter without synchronization.

## Request
Implement `increment()` in `SharedCounter` in `counter.py`.
1. The class has a `self.val` which is a `multiprocessing.Value('i', 0)`.
2. The class has a `self.lock` which is a `multiprocessing.Lock()`.
3. Implement `increment()` to safely increment `self.val.value` by 1.
4. You MUST use the `self.lock` to ensure the operation is atomic.

## Constraints
- ONLY modify `counter.py`.
- You MUST use the `with self.lock:` context manager.

## Verification
Run `python3 test_counter.py`. This script spawns 10 processes that each increment the counter 100 times. The expected result is 1000.
