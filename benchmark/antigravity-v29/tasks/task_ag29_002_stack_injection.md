# Task: Stack Context Injection (task_ag29_002)

## Context
We are implementing a logging utility that needs to capture the "Transaction ID" from the calling function without explicitly passing it through every single function call in the stack.

## Request
Implement `get_context_var(var_name)` in `context_helper.py`.
1. Use `sys._getframe()` or `inspect` to access the caller's frame (the function that called `get_context_var`).
2. Search the caller's local variables for a variable named `var_name`.
3. Return the value of that variable.
4. If the variable is not found in the immediate caller, raise a `LookupError`.

## Constraints
- ONLY modify `context_helper.py`.
- Do NOT use global variables.

## Verification
Run `python3 test_context.py`.
