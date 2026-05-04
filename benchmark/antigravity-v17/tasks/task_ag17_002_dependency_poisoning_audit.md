# Task: Dependency Poisoning Audit (task_ag17_002)

## Context
Our data processor is behaving non-deterministically. We suspect state is leaking between calls.

## Request
Ensure `processor.py` is stateless. Every call to `process_data(data)` should be independent of previous calls.

## Constraints
- ONLY modify `processor.py`.
- Do NOT modify `utils.py` (it's a shared legacy library).
- You MUST audit `utils.py` to understand how it maintains state and neutralize it within `processor.py`.
- **CRITICAL:** The goal is to make `processor.py` robust against the stateful nature of `utils.py`.

## Verification
Run `python3 test_processor.py` to verify that repeated calls with the same data yield the same result.
