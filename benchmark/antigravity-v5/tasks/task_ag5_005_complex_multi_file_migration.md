# Task: Complex Multi-File Migration (task_ag5_005)

## Context
We are refactoring our utility modules to separate legacy and modern code.

## Request
Move the functions `helper_a` and `helper_b` from `legacy_utils.py` to `modern_utils.py`.
The function `helper_c` MUST remain in `legacy_utils.py`.

## Constraints
- Ensure that `modern_utils.py` is fully functional and all internal dependencies are correctly resolved.
- Update any necessary imports.
- Do not change the logic of the functions.
