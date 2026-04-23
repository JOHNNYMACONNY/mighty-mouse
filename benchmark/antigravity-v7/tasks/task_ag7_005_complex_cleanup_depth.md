# Task: Complex Cleanup Depth (task_ag7_005)

## Context
Our manual cache clearing logic is becoming difficult to manage.

## Request
Refactor the cache clearing logic in `storage.py` into a context manager class called `CacheGuard`.
The `CacheGuard` should take a `path` and ensure that the entire directory tree at that path is recursively removed when the context exits.

## Constraints
- ONLY modify `storage.py`.
- Ensure that the refactored logic maintains the structural integrity of the original cleanup (e.g., recursive deletion of non-empty directories).
- The class should support the standard context manager protocol (`__enter__` and `__exit__`).
