# Task: Distributed State Sync (task_ag19_001)

## Context
We have a simulated distributed system with 3 data nodes.

## Request
Implement a transactional update in `coordinator.py`.
1. `update_all(value)`: This should update `node_a.py`, `node_b.py`, and `node_c.py` with the new value.
2. If any node update fails (simulated by an exception), all nodes MUST be reverted to their previous values.
3. You must implement a simple "journal" or "backup" mechanism within the `update_all` function to handle the rollback.

## Constraints
- ONLY modify `coordinator.py`.
- You MUST find the `update_node(val)` function in each node file.
- Node files are in the `nodes/` directory.
- **CRITICAL:** Eventual consistency is NOT allowed here; it must be strictly atomic (all or nothing).

## Verification
Run `python3 test_sync.py`. This script will simulate a failure on the third node and verify that nodes 1 and 2 were correctly rolled back.
