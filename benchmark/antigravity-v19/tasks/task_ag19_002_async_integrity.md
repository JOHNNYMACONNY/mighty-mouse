# Task: Asynchronous Integrity (task_ag19_002)

## Context
Our system must ensure that every database update is accompanied by a successful event broadcast.

## Request
Implement `update_with_event(record_id, value)` in `manager.py`.
1. Update the value in `data_store.py`.
2. Emit an `UPDATE` event via `event_bus.py`.
3. If `event_bus.emit()` fails, you MUST rollback the change in `data_store.py`.

## Constraints
- ONLY modify `manager.py`.
- You MUST find the `data_store` and `event_bus` APIs in the workspace.
- **CRITICAL:** Failure to rollback on event failure will result in inconsistent system state.

## Verification
Run `python3 test_async.py`.
