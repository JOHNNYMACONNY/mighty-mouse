# Task: Async Race Trap (task_ag8_002)

## Context
`counter.py` has a race condition in its `increment` method that causes incorrect totals when multiple tasks run concurrently.

## Request
Fix the `increment()` method in the `GlobalCounter` class to be safe for concurrent asynchronous execution. 

## Constraints
- ONLY modify `counter.py`.
- Ensure that every call to `increment()` is correctly accounted for, even if many calls happen at the same time.
- Avoid using global locks if a class-level or instance-level solution exists.
