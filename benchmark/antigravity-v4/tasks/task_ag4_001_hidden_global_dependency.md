# Task: Hidden Global Dependency (task_ag4_001)

## Context
A global registry of active users is updated by a helper function.

## Request
Refactor `get_users` in `users.py` to return a COPY of the `_active_users` list to prevent accidental mutation from external callers.

## Constraints
- ONLY modify `users.py`.
- Ensure you understand the impact of this change on existing functions in the file.
- Verify whether `register_user` will still function as intended.
