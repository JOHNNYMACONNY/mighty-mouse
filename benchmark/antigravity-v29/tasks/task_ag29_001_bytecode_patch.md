# Task: Runtime Bytecode Patch (task_ag29_001)

## Context
A critical production bug has been identified in a vendor-locked library function. We cannot modify the source code, so we must "hotfix" the function at runtime by replacing its bytecode.

## Request
Implement `hotfix(original_func, fix_func)` in `patcher.py`.
1. The function object `original_func` must remain the same (same `id()`).
2. After calling `hotfix`, any subsequent calls to `original_func` must execute the logic from `fix_func`.
3. Use the `__code__` attribute of the function objects.

## Constraints
- ONLY modify `patcher.py`.
- Do NOT use monkey-patching that replaces the function reference in a module; you MUST replace the internal `__code__` object.

## Verification
Run `python3 test_patch.py`.
