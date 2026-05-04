# Task: Safe Sandbox Exec (task_ag24_001)

## Context
Our platform allows users to submit custom mathematical formulas, but we must ensure they cannot execute malicious system commands.

## Request
Implement `run_safe(code_str)` in `sandbox.py`.
1. Use `exec(code_str, globals_dict)` to execute the code.
2. The `globals_dict` MUST be restricted.
3. Only allow:
    - `math` module (must be imported and included).
    - `abs` (built-in).
4. `__builtins__` MUST be set to an empty dictionary or a very restricted one to prevent access to `eval`, `getattr`, etc.
5. Return the value of a variable named `result` defined in the `code_str`.

## Constraints
- ONLY modify `sandbox.py`.
- If `result` is not defined in the code, return `None`.
- **CRITICAL:** Any access to `os`, `sys`, or `open` must result in a `NameError` or similar failure.

## Verification
Run `python3 test_sandbox.py`.
