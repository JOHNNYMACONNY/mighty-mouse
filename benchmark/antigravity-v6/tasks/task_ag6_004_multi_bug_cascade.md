# Task: Multi-Bug Cascade (task_ag6_004)

## Context
Our email validation logic is letting through malformed addresses.

## Request
Fix the `check_email` function in `validator.py`. 
It MUST correctly identify that addresses with multiple '@' symbols or addresses ending in a dot (e.g., `user@domain.`) are invalid.

## Constraints
- ONLY modify `validator.py`.
- Ensure all edge cases are covered.
- You must verify the fix against multiple invalid patterns and report the results in your RESULT.
