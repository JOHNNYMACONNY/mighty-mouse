# Task: Recursive Metaclass Evolution (task_ag30_002)

## Context
We are building a deeply nested plugin hierarchy. Every plugin, regardless of how deep it is in the inheritance tree, must implement a `run` method.

## Request
Implement `EvolutionMeta` in `evolution.py`.
1. It must be a metaclass.
2. It must validate that any class created using it (except the base `PluginBase`) has a `run` method.
3. If `run` is missing, raise a `TypeError` with the message `"Missing run method"`.
4. Ensure that the metaclass is correctly propagated to all subclasses.

## Constraints
- ONLY modify `evolution.py`.
- You MUST handle deep inheritance (e.g. `Base -> Middle -> Leaf`).

## Verification
Run `python3 test_evolution.py`.
