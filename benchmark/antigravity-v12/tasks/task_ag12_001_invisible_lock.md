# Task: Invisible Global State (task_ag12_001)

## Context
We are seeing intermittent data corruption in our shared counter.

## Request
Implement a thread-safe increment for the `SharedCounter` in `counter.py`.

## Constraints
- ONLY modify `counter.py`.
- You MUST audit the workspace for any global locking mechanisms. If found, you MUST use them.
- If no locking mechanism is found, you MUST implement a local one and state why.
