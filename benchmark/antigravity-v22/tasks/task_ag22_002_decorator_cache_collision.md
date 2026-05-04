# Task: Decorator Cache Collision (task_ag22_002)

## Context
Our `@memoize` decorator incorrectly shares a single cache across all class instances, leading to data leakage between different users.

## Request
Modify the `memoize` decorator in `cache_util.py`.
1. It currently uses a global `_INTERNAL_CACHE`.
2. Refactor it to store the cache on the instance itself (e.g., in `self._memo_cache`).
3. You must initialize `_memo_cache` if it doesn't exist on the instance.

## Constraints
- ONLY modify `cache_util.py`.
- The decorator MUST work for methods (taking `self` as first argument).
- Ensure it handles different arguments correctly (use `*args` as key).

## Verification
Run `python3 test_cache.py`.
