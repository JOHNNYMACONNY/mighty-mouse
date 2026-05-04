# Task: Cascading Type Change (task_ag18_001)

## Context
We are refactoring our ID system to support alphanumeric strings.

## Request
1. Modify `common/utils.py`: Update `get_next_id()` to return a string (e.g., `"ID_001"` instead of `1`).
2. Audit the workspace to find all consumers of `get_next_id()`.
3. Fix all cascading failures caused by this change.

## Constraints
- You MUST update `common/utils.py`.
- You MUST fix all downstream consumers in `service_a/` and `service_b/`.
- Downstream consumers might perform arithmetic (e.g., `id + 1`) or use the ID as a dictionary key that expects an int.

## Verification
Run `python3 test_cascade.py` to verify the entire system is stable.
