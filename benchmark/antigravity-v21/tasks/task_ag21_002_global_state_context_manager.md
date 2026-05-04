# Task: Global State Context Manager (task_ag21_002)

## Context
Our legacy system uses a global buffer that frequently gets corrupted by concurrent operations.

## Request
Implement a context manager `scoped_buffer(temp_data)` in `worker.py`.
1. It must save the current value of `shared_data.BUFFER`.
2. Set `shared_data.BUFFER` to `temp_data`.
3. Yield to the block.
4. Ensure `shared_data.BUFFER` is restored to its original value, even if an exception occurs.

## Constraints
- ONLY modify `worker.py`.
- You MUST use the `contextlib.contextmanager` decorator if possible, or a class-based context manager.

## Verification
Run `python3 test_globals.py`.
