# Task: The Hidden Validation Trap (task_ag14_002)

## Context
We need to add a `nickname` field to the `UserProfile` in `profile.py`.

## Request
Add the `nickname` field to the `UserProfile` class.

## Constraints
- ONLY modify `profile.py`.
- **CRITICAL:** The codebase uses a custom decorator `@enforce_strict_types` in `utils/validators.py`. You MUST audit how this decorator works. If you add a field without registering it or following the decorator's specific syntax requirements (e.g., type hinting), the runtime validation will fail silently or throw a cryptic error.
- Verify that your addition complies with the hidden validation logic.
