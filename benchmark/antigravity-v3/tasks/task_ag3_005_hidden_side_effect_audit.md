# Task: Hidden Side-Effect Audit (task_ag3_005)

## Context
The `utils.format_price` function is used by multiple entry points.

## Request
Update `utils.py` so that `format_price` prepends a `$` symbol to the output.

## Constraints
- Perform an audit of the workspace to see where this function is used.
- Specifically report whether this change will affect the `web.py` output.
- ONLY modify `utils.py`.
