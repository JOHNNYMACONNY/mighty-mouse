# Task: Indirect Registry Corruption (task_ag5_001)

## Context
Our `Registry` class tracks instances of `Service`.

## Request
Add a `shutdown()` method to the `Service` class in `registry.py` that sets `self.active` to `False`.

## Constraints
- ONLY modify `registry.py`.
- Ensure that calling `shutdown()` on a service correctly reflects in the `Registry.get_active()` output.
- Be careful not to introduce any logic that might corrupt the `Registry`'s internal list of services.
