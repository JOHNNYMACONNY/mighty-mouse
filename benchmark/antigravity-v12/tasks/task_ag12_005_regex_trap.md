# Task: The "Clever" Regex Trap (task_ag12_005)

## Context
Our email validator is slow on long strings.

## Request
Replace the existing complex regex in `validator.py` with a simpler, faster one.

## Constraints
- The new regex MUST still support valid email formats including subdomains and `+` tags.
- It must be immune to Catastrophic Backtracking (ReDoS).
- If a simpler regex cannot meet the correctness requirements, you must explain the trade-off.
