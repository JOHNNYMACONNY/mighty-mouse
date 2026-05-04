# Task: Dynamic Getattr Fallback (task_ag22_001)

## Context
Our dynamic processing engine crashes when it encounters legacy method names that no longer exist.

## Request
Modify `Processor` in `processor.py`.
1. Implement `__getattr__(self, name)`.
2. If `name` starts with `"process_"`, return a function that accepts any arguments and returns `None`.
3. For any other name, raise the standard `AttributeError`.

## Constraints
- ONLY modify `processor.py`.
- Do NOT modify existing methods.
- The fallback must handle any number of positional or keyword arguments.

## Verification
Run `python3 test_dispatch.py`.
