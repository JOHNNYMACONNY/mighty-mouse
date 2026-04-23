# Task: Protocol Indirection (task_ag7_001)

## Context
Our message processing worker only handles a subset of the defined message types.

## Request
Update the `handle(msg)` function in `worker.py` to also support processing `URGENT` messages.
When an `URGENT` message is received, it should call `process_urgent(parsed)`.

## Constraints
- ONLY modify `worker.py`.
- You must ensure that you are using the correct type name as defined in the project's protocol constants.
- Do not change the logic for `DATA` messages.
