# Task: Silent Ordering Regression (task_ag7_002)

## Context
The `get_recent_actions` function is currently losing the chronological order of user actions during deduplication.

## Request
Fix the `get_recent_actions` function in `history.py` to remove duplicate actions while strictly preserving their original relative order (most recent first).

## Constraints
- ONLY modify `history.py`.
- The input list `actions` is ordered with the most recent action at the first index (index 0).
- The output must be a list containing unique elements in the same relative order as the input.
