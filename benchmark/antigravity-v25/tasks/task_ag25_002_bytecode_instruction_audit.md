# Task: Bytecode Instruction Audit (task_ag25_002)

## Context
We are building a plugin system that requires "pure" functions (no global state modification). We need to audit the bytecode of submitted functions.

## Request
Implement `is_pure(func)` in `auditor.py`.
1. Use the `dis` module to inspect the bytecode instructions of `func`.
2. If any instruction in the function is `"STORE_GLOBAL"` or `"DELETE_GLOBAL"`, return `False`.
3. Otherwise, return `True`.

## Constraints
- ONLY modify `auditor.py`.
- You MUST use `dis.get_instructions(func)` or a similar standard library method for introspection.

## Verification
Run `python3 test_bytecode.py`.
