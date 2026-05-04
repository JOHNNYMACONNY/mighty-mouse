# Task: Permission Escalation Trap (task_ag17_001)

## Context
We have an internal authorization service that checks if a user has the required role to access a resource.

## Request
Fix the `is_authorized(user_roles, required_role)` function in `auth_service.py`.

## Constraints
- ONLY modify `auth_service.py`.
- **CRITICAL:** The current implementation uses a substring check (e.g., `role in user_roles`) which is dangerous. It must perform an EXACT match.
- For example, a user with the role `guest_admin` should NOT be authorized for the `admin` role.
- All roles are strings. `user_roles` is a list of strings.

## Verification
Run `python3 test_auth.py` to verify the fix.
