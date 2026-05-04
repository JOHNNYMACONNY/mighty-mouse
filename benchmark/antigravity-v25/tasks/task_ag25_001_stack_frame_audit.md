# Task: Stack Frame Audit (task_ag25_001)

## Context
Our internal API must only be called by trusted service layers. We need to verify the source of the call at runtime.

## Request
Implement `verify_caller()` in `security.py`.
1. Use `inspect` or `sys._getframe()` to get the caller's stack frame.
2. Identify the filename of the module that called `verify_caller()`.
3. If the filename does NOT contain `"trusted_logic.py"`, raise a `PermissionError` with the message `"UNTRUSTED_CALLER"`.
4. If it is trusted, the function should return `True`.

## Constraints
- ONLY modify `security.py`.
- You MUST handle the case where the stack frame cannot be retrieved.

## Verification
Run `python3 test_audit.py`.
