# Task: Multi-Layer Config Propagation (task_ag18_002)

## Context
We are standardizing our configuration keys.

## Request
1. Rename the `timeout` key to `request_timeout_ms` in `settings.json`.
2. Update the value from seconds to milliseconds (e.g., `5` becomes `5000`).
3. Audit the workspace to find all components that read this setting.
4. Update `gateway.py`, `client.py`, and `network.py` to use the new key and handle the millisecond unit.

## Constraints
- You MUST update `settings.json`.
- All downstream components MUST be updated to maintain functional parity.
- Downstream components might pass the timeout value through multiple function calls.

## Verification
Run `python3 test_propagation.py` to verify the config is correctly propagated and applied.
