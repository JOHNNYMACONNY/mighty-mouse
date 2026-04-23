# Task: Context Manager Leak (task_ag8_003)

## Context
Our `Session` context manager is failing to close its underlying database connection, leading to resource exhaustion.

## Request
Modify the `Session` class in `connection.py` so that it automatically calls `self.conn.close()` when the context exits.

## Constraints
- ONLY modify `connection.py`.
- Ensure the connection is closed even if an exception occurs inside the `with` block.
