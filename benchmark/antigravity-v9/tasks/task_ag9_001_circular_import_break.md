# Task: Circular Import Break (task_ag9_001)

## Context
Our `auth.py` module needs to know about the `User` class for type hinting, but `user.py` already imports from `auth.py`.

## Request
Update the `check_permission(user)` function in `auth.py` to include a proper type hint for the `user` parameter. The type should be the `User` class defined in `user.py`.

## Constraints
- ONLY modify `auth.py`.
- You MUST ensure that your changes do not introduce a runtime circular import error.
- Use standard Python patterns for resolving circular dependencies in type hints.
