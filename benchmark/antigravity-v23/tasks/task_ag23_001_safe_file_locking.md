# Task: Safe File Locking (task_ag23_001)

## Context
Our logging system suffers from corrupted logs when multiple processes write to the same file simultaneously.

## Request
Implement `atomic_append(filename, content)` in `file_utils.py`.
1. Before writing, check for the existence of `{filename}.lock`.
2. If it exists, wait (print `LOCK_HELD_RETRYING`) and retry up to 5 times.
3. If it doesn't exist, create it (write `"LOCKED"` to it).
4. Append the `content` + `\n` to `filename`.
5. Remove the lock file.
6. **CRITICAL:** Use a `try...finally` block to ensure the lock file is ALWAYS removed, even if the write fails.

## Constraints
- ONLY modify `file_utils.py`.
- You MUST handle the case where the lock file cannot be removed (e.g. permission error) gracefully by printing `CLEANUP_FAILED`.

## Verification
Run `python3 test_locking.py`. This script simulates a concurrent write by creating a lock file manually.
