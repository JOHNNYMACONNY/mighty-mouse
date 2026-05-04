# Task: Shared Manager Eviction (task_ag28_002)

## Context
Our shared cache is growing indefinitely and causing workers to run out of memory. We need a fixed-size shared cache.

## Request
Implement `LimitedSharedDict` in `cache_manager.py`.
1. It should take a `shared_dict` (from `Manager().dict()`) and `max_keys` in its constructor.
2. Implement `set(key, value)`.
3. If `key` is new and adding it would exceed `max_keys`, remove the key that was added first (FIFO).
4. You may need an internal `list` (also shared) to track the order of keys.

## Constraints
- ONLY modify `cache_manager.py`.
- Ensure the eviction logic is atomic if possible (use a `Lock` if needed, the class has `self.lock`).

## Verification
Run `python3 test_cache.py`.
