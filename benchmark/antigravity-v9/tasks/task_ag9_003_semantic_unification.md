# Task: Semantic Unification (task_ag9_003)

## Context
Our pricing logic is scattered across multiple specialized functions.

## Request
Refactor `pricing.py` to use a single `get_price(base, region)` function instead of `get_us_price` and `get_eu_price`.
- Locale 'US' should use the logic from `get_us_price`.
- Locale 'EU' should use the logic from `get_eu_price`.

## Constraints
- ONLY modify `pricing.py`.
- Ensure that the new `get_price` function correctly routes based on the `region` string.
- You must remove the old, redundant functions.
