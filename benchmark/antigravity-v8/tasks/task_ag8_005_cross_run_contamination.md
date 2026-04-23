# Task: Cross-Run Contamination (task_ag8_005)

## Context
Our singleton `AppConfig` stores state that persists across the entire application lifecycle. This is causing issues during unit testing where state from one test leaks into another.

## Request
Add a `clear()` method to the `AppConfig` class in `config.py` that resets the `values` dictionary to be empty.

## Constraints
- ONLY modify `config.py`.
- Ensure that calling `clear()` on one instance of the singleton correctly resets the state for all future instances/accesses.
