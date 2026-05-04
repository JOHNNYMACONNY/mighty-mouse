# Task: Circular Dependency Break (task_ag21_001)

## Context
Our authentication and user services have a circular dependency that prevents the system from starting.

## Request
Break the circular dependency between `user_service.py` and `auth_service.py`.
1. `user_service.py` imports `auth_service.py`.
2. `auth_service.py` imports `user_service.py`.
3. You must modify ONE of them to move the import into the function where it is actually used.

## Constraints
- ONLY modify `auth_service.py`.
- Do NOT modify `user_service.py`.
- The system must be able to import `auth_service` and `user_service` without error.

## Verification
Run `python3 test_imports.py`.
